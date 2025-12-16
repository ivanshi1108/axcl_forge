import os
import shutil
import sys

# Configuration
ROOTFS_DIR = os.environ.get("ROOTFS_DIR", "rootfs")
TEMP_DIR = os.environ.get("TEMP_DIR", "temp_ubuntu")

# Core libraries to upgrade
# These are the base names we look for in library paths
CORE_LIB_NAMES = [
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
]

def require_extracted_root():
    if not os.path.isdir(TEMP_DIR):
        sys.exit(f"Error: {TEMP_DIR} not found; run custom_enter.sh to prepare the Ubuntu base first")

def find_library(lib_name, search_paths):
    for path in search_paths:
        full_path = os.path.join(path, lib_name)
        if os.path.lexists(full_path): # Use lexists to find symlinks too
            return full_path
    return None

def resolve_symlinks(start_path, root_dir):
    """
    Returns a set of paths (relative to root_dir) that need to be copied,
    including the start_path and any targets if it is a symlink.
    """
    paths_to_copy = set()
    
    # Add the file itself
    rel_path = os.path.relpath(start_path, root_dir)
    paths_to_copy.add(rel_path)
    
    if os.path.islink(start_path):
        link_target = os.readlink(start_path)
        # Link target might be absolute (relative to root) or relative
        if os.path.isabs(link_target):
            # If absolute, it's relative to the temp_ubuntu root
            # e.g. /lib/aarch64-linux-gnu/libc-2.35.so -> temp_ubuntu/lib/aarch64-linux-gnu/libc-2.35.so
            # But we need to be careful about how it's constructed
            target_full_path = os.path.join(root_dir, link_target.lstrip('/'))
        else:
            # Relative to the symlink's directory
            target_full_path = os.path.join(os.path.dirname(start_path), link_target)
        
        # Normalize path
        target_full_path = os.path.normpath(target_full_path)
        
        if os.path.lexists(target_full_path):
            # Recursively resolve
            paths_to_copy.update(resolve_symlinks(target_full_path, root_dir))
        else:
            print(f"Warning: Symlink target {target_full_path} does not exist")
            
    return paths_to_copy

def copy_file(src, dest):
    if os.path.lexists(dest):
        os.remove(dest)
    
    if os.path.islink(src):
        link_target = os.readlink(src)
        os.symlink(link_target, dest)
    else:
        shutil.copy2(src, dest)

def main():
    require_extracted_root()

    lib_search_paths = [
        os.path.join(TEMP_DIR, "lib/aarch64-linux-gnu"),
        os.path.join(TEMP_DIR, "usr/lib/aarch64-linux-gnu"),
        os.path.join(TEMP_DIR, "lib"),
        os.path.join(TEMP_DIR, "usr/lib"),
    ]

    files_to_copy = set()

    print("Locating core libraries...")
    for lib_name in CORE_LIB_NAMES:
        lib_path = find_library(lib_name, lib_search_paths)
        if lib_path:
            # Resolve symlinks and add all involved files
            files = resolve_symlinks(lib_path, TEMP_DIR)
            files_to_copy.update(files)
        else:
            print(f"Warning: Could not find core library {lib_name}")

    print(f"Found {len(files_to_copy)} files to copy (libs + symlink targets).")

    print("Copying files...")
    for rel_path in files_to_copy:
        src = os.path.join(TEMP_DIR, rel_path)
        
        # Determine destination
        dest_rel = rel_path
        if "aarch64-linux-gnu" in dest_rel:
            dest_rel = dest_rel.replace("aarch64-linux-gnu/", "")
        
        dest = os.path.join(ROOTFS_DIR, dest_rel)
        
        dest_dir = os.path.dirname(dest)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
            
        try:
            copy_file(src, dest)
            print(f"Copied {rel_path}")
        except Exception as e:
            print(f"Error copying {src} to {dest}: {e}")

    print("Done. Core libraries upgraded.")

if __name__ == "__main__":
    main()
