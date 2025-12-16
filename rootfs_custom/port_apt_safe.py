import os
import subprocess
import shutil
import sys

# Configuration
ROOTFS_DIR = os.environ.get("ROOTFS_DIR", "rootfs")
TEMP_DIR = os.environ.get("TEMP_DIR", "temp_ubuntu")
APT_PRIVATE_DIR = "usr/lib/apt-private"
APT_PRIVATE_LIB_DIR = os.path.join(APT_PRIVATE_DIR, "lib")
APT_PRIVATE_BIN_DIR = os.path.join(APT_PRIVATE_DIR, "bin")

# Binaries to install in /usr/bin (Wrappers)
PUBLIC_BINARIES = [
    "usr/bin/apt",
    "usr/bin/apt-get",
    "usr/bin/apt-cache",
    "usr/bin/apt-key",
    "usr/bin/apt-config",
    "usr/bin/apt-mark",
    "usr/bin/dpkg",
    "usr/bin/dpkg-deb",
    "usr/bin/dpkg-split",
    "usr/bin/dpkg-trigger",
    "usr/bin/dpkg-query",
    "usr/bin/dpkg-divert",
    "usr/bin/dpkg-statoverride",
    "usr/bin/dpkg-maintscript-helper",
    "usr/bin/dpkg-realpath",
    "usr/bin/tar",
    "usr/bin/sed",
    "usr/bin/grep",
    "usr/bin/mawk",
    "usr/bin/find",
    "usr/bin/diff",
    "usr/bin/gzip",
    "usr/bin/cp",
    "usr/bin/mv",
    "usr/bin/rm",
    "usr/bin/ls",
    "usr/bin/date",
    "usr/bin/sleep",
    "usr/bin/sort",
    "usr/bin/tr",
    "usr/bin/cut",
    "usr/bin/wc",
    "usr/bin/head",
    "usr/bin/tail",
    "usr/bin/uniq",
    "usr/bin/basename",
    "usr/bin/dirname",
    "usr/bin/cat",
    "usr/bin/chown",
    "usr/bin/chmod",
    "usr/bin/mkdir",
]

# Binaries to install in /sbin (No wrappers, system binaries)
SYSTEM_BINARIES = [
    "sbin/ldconfig",
    "sbin/ldconfig.real",
]

# Binaries to install in /usr/lib/apt-private/bin (Hidden from system)
PRIVATE_BINARIES = [
    "usr/bin/gpgv",
]

# Core libraries that are ALREADY upgraded in rootfs/lib
CORE_LIBS = {
    "libc.so.6",
    "libm.so.6",
    "libdl.so.2",
    "libpthread.so.0",
    "librt.so.1",
    "libresolv.so.2",
    "libutil.so.1",
    "libstdc++.so.6",
    "libgcc_s.so.1",
    "ld-linux-aarch64.so.1"
}

# Additional directories to copy
TARGET_DIRS = [
    "etc/apt",
    "var/lib/apt",
    "var/lib/dpkg",
    "usr/lib/apt", # Methods
    "usr/share/dpkg",
    "usr/share/keyrings",
]


def require_extracted_root():
    if not os.path.isdir(TEMP_DIR):
        sys.exit(f"Error: {TEMP_DIR} not found; run custom_enter.sh to prepare the Ubuntu base first")

def get_dependencies(binary_path):
    deps = set()
    try:
        result = subprocess.run(
            ["readelf", "-d", binary_path], 
            capture_output=True, 
            text=True, 
            check=True
        )
        for line in result.stdout.splitlines():
            if "Shared library" in line:
                parts = line.split("[")
                if len(parts) > 1:
                    lib_name = parts[1].split("]")[0]
                    deps.add(lib_name)
    except subprocess.CalledProcessError:
        pass
    return deps

def find_library(lib_name, search_paths):
    for path in search_paths:
        full_path = os.path.join(path, lib_name)
        if os.path.lexists(full_path):
            return full_path
    return None

def resolve_symlinks(start_path, root_dir):
    paths_to_copy = set()
    rel_path = os.path.relpath(start_path, root_dir)
    paths_to_copy.add(rel_path)
    
    if os.path.islink(start_path):
        link_target = os.readlink(start_path)
        if os.path.isabs(link_target):
            target_full_path = os.path.join(root_dir, link_target.lstrip('/'))
        else:
            target_full_path = os.path.join(os.path.dirname(start_path), link_target)
        
        target_full_path = os.path.normpath(target_full_path)
        if os.path.lexists(target_full_path):
            paths_to_copy.update(resolve_symlinks(target_full_path, root_dir))
            
    return paths_to_copy

def copy_file(src, dest):
    if os.path.lexists(dest):
        os.remove(dest)
    if os.path.islink(src):
        link_target = os.readlink(src)
        os.symlink(link_target, dest)
    else:
        shutil.copy2(src, dest)

def create_wrapper(binary_name, dest_dir, is_private=False):
    wrapper_path = os.path.join(dest_dir, binary_name)
    real_binary = f"{binary_name}.real"
    
    # For private binaries, they are in the same dir
    # For public binaries, they are in /usr/bin, but we want them to use private bin path
    
    private_bin_path = f"/{APT_PRIVATE_BIN_DIR}"
    private_lib_path = f"/{APT_PRIVATE_LIB_DIR}"
    
    if is_private:
        # Wrapper in private dir calling .real in same dir
        content = f"""#!/bin/sh
export LD_LIBRARY_PATH={private_lib_path}:$LD_LIBRARY_PATH
export PATH={private_bin_path}:$PATH
exec {private_bin_path}/{real_binary} "$@"
"""
    else:
        # Wrapper in /usr/bin calling .real in /usr/bin (for apt)
        # But adding private bin to PATH
        content = f"""#!/bin/sh
export LD_LIBRARY_PATH={private_lib_path}:$LD_LIBRARY_PATH
export PATH={private_bin_path}:$PATH
exec /usr/bin/{real_binary} "$@"
"""

    if os.path.lexists(wrapper_path):
        os.remove(wrapper_path)

    with open(wrapper_path, "w") as f:
        f.write(content)
    os.chmod(wrapper_path, 0o755)
    print(f"Created wrapper for {binary_name} in {dest_dir}")

def main():
    require_extracted_root()

    lib_search_paths = [
        os.path.join(TEMP_DIR, "lib/aarch64-linux-gnu"),
        os.path.join(TEMP_DIR, "usr/lib/aarch64-linux-gnu"),
        os.path.join(TEMP_DIR, "lib"),
        os.path.join(TEMP_DIR, "usr/lib"),
    ]

    # 1. Identify all needed libraries
    libs_needed = set()
    files_to_process = set()
    
    all_binaries = PUBLIC_BINARIES + PRIVATE_BINARIES + SYSTEM_BINARIES
    for binary in all_binaries:
        files_to_process.add(os.path.join(TEMP_DIR, binary))

    apt_methods_dir = os.path.join(TEMP_DIR, "usr/lib/apt/methods")
    if os.path.exists(apt_methods_dir):
        for f in os.listdir(apt_methods_dir):
            files_to_process.add(os.path.join(apt_methods_dir, f))

    processed_files = set()
    
    print("Resolving dependencies...")
    while files_to_process:
        current_file = files_to_process.pop()
        if current_file in processed_files:
            continue
        processed_files.add(current_file)
        
        if os.path.isfile(current_file):
            try:
                with open(current_file, 'rb') as f:
                    if f.read(4) == b'\x7fELF':
                        deps = get_dependencies(current_file)
                        for dep in deps:
                            if dep not in CORE_LIBS:
                                if dep not in libs_needed:
                                    libs_needed.add(dep)
                                    lib_path = find_library(dep, lib_search_paths)
                                    if lib_path:
                                        files_to_process.add(lib_path)
            except Exception:
                pass

    print(f"Found {len(libs_needed)} non-core libraries needed.")

    # 2. Copy Libraries to APT_PRIVATE_LIB_DIR
    print(f"Copying libraries to {APT_PRIVATE_LIB_DIR}...")
    dest_lib_dir = os.path.join(ROOTFS_DIR, APT_PRIVATE_LIB_DIR)
    if not os.path.exists(dest_lib_dir):
        os.makedirs(dest_lib_dir)

    for lib_name in libs_needed:
        lib_path = find_library(lib_name, lib_search_paths)
        if lib_path:
            files = resolve_symlinks(lib_path, TEMP_DIR)
            for rel_path in files:
                src = os.path.join(TEMP_DIR, rel_path)
                filename = os.path.basename(rel_path)
                dest = os.path.join(dest_lib_dir, filename)
                copy_file(src, dest)
        else:
            print(f"Warning: Could not find library {lib_name}")

    # 3. Copy Binaries
    print("Copying binaries...")
    
    # Public binaries (apt, etc.) -> /usr/bin
    dest_public = os.path.join(ROOTFS_DIR, "usr/bin")
    if not os.path.exists(dest_public):
        os.makedirs(dest_public)
        
    for binary_rel in PUBLIC_BINARIES:
        src = os.path.join(TEMP_DIR, binary_rel)
        binary_name = os.path.basename(binary_rel)
        dest_real = os.path.join(dest_public, f"{binary_name}.real")
        copy_file(src, dest_real)
        os.chmod(dest_real, 0o755)
        create_wrapper(binary_name, dest_public, is_private=False)
        
        # Also remove /bin/<binary> if it exists (busybox symlink)
        bin_symlink = os.path.join(ROOTFS_DIR, "bin", binary_name)
        if os.path.lexists(bin_symlink):
            os.remove(bin_symlink)
            # Create symlink from /bin/<binary> to /usr/bin/<binary>
            # This ensures scripts using /bin/tar still work and use our wrapper
            os.symlink(f"/usr/bin/{binary_name}", bin_symlink)
            print(f"Replaced /bin/{binary_name} with symlink to /usr/bin/{binary_name}")

    # Private binaries (dpkg, gpgv) -> /usr/lib/apt-private/bin
    dest_private = os.path.join(ROOTFS_DIR, APT_PRIVATE_BIN_DIR)
    if not os.path.exists(dest_private):
        os.makedirs(dest_private)
        
    for binary_rel in PRIVATE_BINARIES:
        src = os.path.join(TEMP_DIR, binary_rel)
        binary_name = os.path.basename(binary_rel)
        dest_real = os.path.join(dest_private, f"{binary_name}.real")
        copy_file(src, dest_real)
        os.chmod(dest_real, 0o755)
        create_wrapper(binary_name, dest_private, is_private=True)

    # System binaries (ldconfig) -> /sbin
    dest_sbin = os.path.join(ROOTFS_DIR, "sbin")
    if not os.path.exists(dest_sbin):
        os.makedirs(dest_sbin)
        
    for binary_rel in SYSTEM_BINARIES:
        src = os.path.join(TEMP_DIR, binary_rel)
        binary_name = os.path.basename(binary_rel)
        dest = os.path.join(dest_sbin, binary_name)
        copy_file(src, dest)
        os.chmod(dest, 0o755)
        print(f"Copied system binary {binary_name} to {dest_sbin}")

    # 4. Copy Configs and Data
    print("Copying configurations and data...")
    for d in TARGET_DIRS:
        src_dir = os.path.join(TEMP_DIR, d)
        if os.path.exists(src_dir):
            for root, dirs, files in os.walk(src_dir):
                rel_root = os.path.relpath(root, TEMP_DIR)
                dest_root = os.path.join(ROOTFS_DIR, rel_root)
                if not os.path.exists(dest_root):
                    os.makedirs(dest_root)
                
                for f in files:
                    src_file = os.path.join(root, f)
                    dest_file = os.path.join(dest_root, f)
                    # Don't overwrite existing files in /var/lib/dpkg if they exist?
                    # Actually, we want to populate it if empty.
                    # If it exists and is not empty, we might be overwriting.
                    # But for now, let's assume we need the Ubuntu structure.
                    copy_file(src_file, dest_file)
                
                for l in dirs:
                    d_path = os.path.join(dest_root, l)
                    if not os.path.exists(d_path):
                        os.makedirs(d_path)

    # 5. Configure APT to use private dpkg
    print("Configuring APT...")
    apt_conf_dir = os.path.join(ROOTFS_DIR, "etc/apt/apt.conf.d")
    if not os.path.exists(apt_conf_dir):
        os.makedirs(apt_conf_dir)
    
    # Create symlink for awk -> mawk if we installed mawk
    if "usr/bin/mawk" in PUBLIC_BINARIES:
        awk_link = os.path.join(ROOTFS_DIR, "usr/bin/awk")
        if os.path.lexists(awk_link):
            os.remove(awk_link)
        os.symlink("mawk", awk_link)
        print("Created symlink /usr/bin/awk -> mawk")

    with open(os.path.join(apt_conf_dir, "00dpkg-path"), "w") as f:
        # dpkg is now in /usr/bin (wrapper), so we don't need to override it.
        # f.write(f'Dir::Bin::dpkg "/{APT_PRIVATE_BIN_DIR}/dpkg";\n')
        # f.write(f'Dir::Bin::dpkg-deb "/{APT_PRIVATE_BIN_DIR}/dpkg-deb";\n')
        f.write(f'Dir::Bin::gpg "/{APT_PRIVATE_BIN_DIR}/gpgv";\n') # apt uses gpgv for verification

    # Remove dpkg-preconfigure config if it exists, as we don't have perl
    debconf_config = os.path.join(apt_conf_dir, "70debconf")
    if os.path.exists(debconf_config):
        os.remove(debconf_config)
        print("Removed 70debconf to disable dpkg-preconfigure")

    # Create dummy debconf/confmodule to satisfy postinst scripts
    debconf_dir = os.path.join(ROOTFS_DIR, "usr/share/debconf")
    if not os.path.exists(debconf_dir):
        os.makedirs(debconf_dir)
    
    confmodule_path = os.path.join(debconf_dir, "confmodule")
    with open(confmodule_path, "w") as f:
        f.write("""#!/bin/sh
# Dummy debconf library for minimal systems

db_set() { :; }
db_input() { :; }
db_go() { :; }
db_get() { RET=""; :; }
db_stop() { :; }
db_version() { :; }
db_capb() { :; }
db_register() { :; }
db_unregister() { :; }
db_reset() { :; }
db_subst() { :; }
db_fset() { :; }
db_metaget() { RET=""; :; }
db_purge() { :; }
db_x_loadtemplatefile() { :; }
""")
    os.chmod(confmodule_path, 0o755)
    print("Created dummy /usr/share/debconf/confmodule")

    # Configure ld.so.conf for multiarch support (Critical for finding installed libs)
    ld_conf_path = os.path.join(ROOTFS_DIR, "etc/ld.so.conf")
    if not os.path.exists(ld_conf_path):
        with open(ld_conf_path, "w") as f:
            f.write("include /etc/ld.so.conf.d/*.conf\n")
    
    ld_conf_d = os.path.join(ROOTFS_DIR, "etc/ld.so.conf.d")
    if not os.path.exists(ld_conf_d):
        os.makedirs(ld_conf_d)
        
    with open(os.path.join(ld_conf_d, "aarch64-linux-gnu.conf"), "w") as f:
        f.write("# Multiarch support\n")
        f.write("/usr/local/lib/aarch64-linux-gnu\n")
        f.write("/lib/aarch64-linux-gnu\n")
        f.write("/usr/lib/aarch64-linux-gnu\n")
    print("Configured /etc/ld.so.conf for multiarch library support")

    # 6. System Configuration
    print("Configuring system...")
    passwd_path = os.path.join(ROOTFS_DIR, "etc/passwd")
    if os.path.exists(passwd_path):
        with open(passwd_path, 'r') as f:
            content = f.read()
        if "_apt:" not in content:
            with open(passwd_path, 'a') as f:
                if not content.endswith('\n'):
                    f.write('\n')
                f.write("_apt:x:100:65534::/nonexistent:/usr/sbin/nologin\n")
    
    shadow_path = os.path.join(ROOTFS_DIR, "etc/shadow")
    if os.path.exists(shadow_path):
        with open(shadow_path, 'r') as f:
            content = f.read()
        if "_apt:" not in content:
            with open(shadow_path, 'a') as f:
                if not content.endswith('\n'):
                    f.write('\n')
                f.write("_apt:*:19000:0:99999:7:::\n")

    for d in ["var/cache/apt/archives/partial", "var/log/apt", "tmp"]:
        path = os.path.join(ROOTFS_DIR, d)
        if not os.path.exists(path):
            os.makedirs(path)
            
    tmp_path = os.path.join(ROOTFS_DIR, "tmp")
    os.chmod(tmp_path, 0o1777)

    print("Done. APT installed in SAFE side-load mode.")

if __name__ == "__main__":
    main()
