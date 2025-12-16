#!/bin/bash
set -e

# Parse command-line argument for ext4 size (default 512M, minimum 128M)
SIZE=${1:-512M}
NUM=$(echo $SIZE | sed 's/M$//')
if ! [[ $NUM =~ ^[0-9]+$ ]] || [ $NUM -lt 128 ]; then
    echo "Error: Size must be at least 128M (e.g., 256M, 512M)" >&2
    exit 1
fi

# This script sets up a minimal rootfs by porting APT and dependencies from Ubuntu 22.04,
# configuring the system for network, SSH, and application deployment, then chroots into
# the rootfs to install additional software, enabling automatic startup of web services.

echo "Starting rootfs setup and APT porting process with size $SIZE..."

# Ensure `rsync` is available on the host. If missing, try to install via apt.
if ! command -v rsync >/dev/null 2>&1; then
    echo "rsync not found — attempting to install via apt-get"
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update
        sudo DEBIAN_FRONTEND=noninteractive apt-get install -y rsync || {
            echo "Failed to install rsync via apt-get; please install rsync manually." >&2
            exit 1
        }
    else
        echo "apt-get not available; please install 'rsync' manually and re-run this script." >&2
        exit 1
    fi
fi

# Step 1: Clean up and extract tarballs
sudo ./ch-mount.sh -u rootfs/ || { echo "Warning: ch-mount -u rootfs/ failed, continuing" >&2; }
sudo rm -rf rootfs temp_ubuntu

echo "Extracting ubuntu-base-22.04.5-base-arm64.tar.gz..."
mkdir -p temp_ubuntu
tar xf ubuntu-base-22.04.5-base-arm64.tar.gz -C temp_ubuntu

IMAGE_NAME="rootfs_origin.ext4"
MOUNT_POINT="$(pwd)/mnt_rootfs_tmp"

if [ -f "$IMAGE_NAME" ]; then
    echo "Found $IMAGE_NAME — mounting and copying to rootfs/"
    mkdir -p "$MOUNT_POINT"
    mkdir -p rootfs
    if sudo mount -o loop "$IMAGE_NAME" "$MOUNT_POINT"; then
        echo "Mounted $IMAGE_NAME to $MOUNT_POINT — copying files to rootfs/"
        sudo rsync -aHAX --numeric-ids --delete  "$MOUNT_POINT/" rootfs/
        sudo umount "$MOUNT_POINT" || { echo "Warning: failed to unmount $MOUNT_POINT" >&2; }
        rmdir "$MOUNT_POINT" 2>/dev/null || true
        sudo chown -R "$(id -u):$(id -g)" rootfs
    else
        echo "Error: failed to mount $IMAGE_NAME" >&2
        exit 1
    fi
else
    echo "Error: $IMAGE_NAME not found — aborting (rootfs-3.10.2.tar.gz support removed)" >&2
    exit 1
fi

# Step 2: Upgrade core libraries (glibc, libstdc++, etc.)
if [ -f "port_libs_only.py" ]; then
    echo "Step 2: Upgrading core libraries..."
    python3 port_libs_only.py
else
    echo "Error: port_libs_only.py not found!"
    exit 1
fi

# Step 3: Install APT and dependencies in side-load mode
if [ -f "port_apt_safe.py" ]; then
    echo "Step 3: Installing APT in safe side-load mode..."
    python3 port_apt_safe.py
else
    echo "Error: port_apt_safe.py not found!"
    exit 1
fi

# Step 4: Ensure bash and update-alternatives are present in target rootfs
echo "Ensuring /usr/bin/bash and update-alternatives..."
mkdir -p rootfs/usr/bin
for bin in bash update-alternatives; do
    src="temp_ubuntu/usr/bin/${bin}"
    if [ -f "$src" ]; then
        cp -a "$src" rootfs/bin/
        echo "Copied $bin"
    else
        echo "Warning: $bin not found in temp_ubuntu; skipped"
    fi
done


# Step 5: Copy minimal curl runtime dependencies (avoid touching glibc/ld)
echo "Copying curl runtime dependencies..."
mkdir -p rootfs/usr/lib
libs=(
  libidn2.so.0.3.7
  libidn2.so.0
  libunistring.so.2.2.0
  libunistring.so.2
  libzstd.so.1.4.8
  libzstd.so.1
  libssl.so.3
  libcrypto.so.3
  libkrb5.so.3.3
  libkrb5.so.3
  libk5crypto.so.3.1
  libk5crypto.so.3
  libkrb5support.so.0.1
  libkrb5support.so.0
  libgssapi_krb5.so.2.2
  libgssapi_krb5.so.2
  libkeyutils.so.1.9
  libkeyutils.so.1
)
for f in "${libs[@]}"; do
    src="temp_ubuntu/usr/lib/aarch64-linux-gnu/$f"
    if [ -f "$src" ]; then
        cp -a "$src" rootfs/usr/lib/
        echo "Copied $f"
    else
        echo "Warning: $f not found in temp_ubuntu; skipped"
    fi
done

# Step 6: Copy libaudit runtime (explicit dependency)
echo "Copying libaudit runtime..."
audit_src_dir="temp_ubuntu/usr/lib/aarch64-linux-gnu"
if compgen -G "${audit_src_dir}/libaudit.so.*" >/dev/null; then
    cp -a ${audit_src_dir}/libaudit.so.* rootfs/usr/lib/
    echo "Copied libaudit.so.*"
else
    echo "Warning: libaudit.so.* not found in ${audit_src_dir}; skipped"
fi

# Step 7: Configure CA certificates
echo "Copy ca-certificates.conf..."
cp ca-certificates.conf rootfs/etc/ca-certificates.conf

# Step 8: Configure system startup, runtime environment, and deploy required tools/models
echo "/soc/scripts/pcie_net2.sh slave" >> rootfs/etc/init.d/rcS
echo "ip route add default via 192.168.1.2 dev ax-net0" >> rootfs/etc/init.d/rcS

printf '%s\n' 'echo 1 > /proc/ax_proc/npu/enable' >> rootfs/etc/profile

echo "python3 -m http.server 8080 --directory /root/app/dist/ >> /var/log/frontend.log 2>&1 &" >> rootfs/etc/init.d/rcS
echo "export PYTHONPATH=/root/app/" >> rootfs/etc/init.d/rcS
echo "export LD_LIBRARY_PATH=/usr/lib/apt-private/lib:/usr/local/lib:/usr/lib:/opt/lib:/soc/lib" >> rootfs/etc/init.d/rcS
echo "uvicorn main:app --host 0.0.0.0 --port 8016 >> /var/log/backend.log 2>&1 &" >> rootfs/etc/init.d/rcS

printf '%s\n' 'export LD_LIBRARY_PATH=/usr/lib/apt-private/lib:$LD_LIBRARY_PATH' >> rootfs/etc/profile

cp sshd rootfs/usr/sbin/sshd
cp ssh-keygen rootfs/usr/bin/ssh-keygen
cp S50sshd rootfs/etc/init.d/S50sshd
cp -R ssh rootfs/etc/

cp get-pip.py rootfs/get-pip.py
cp axengine-0.1.3-py3-none-any.whl rootfs/axengine-0.1.3-py3-none-any.whl
cp ../axcl_studio/server-backend/requirements.txt rootfs/requirements.txt

sudo mkdir -p rootfs/root/file_storage/models/
sudo cp yolov5s.axmodel rootfs/root/file_storage/models/yolov5s.axmodel

mkdir rootfs/root/app
cp -R ../axcl_studio/web-frontend/dist/ rootfs/root/app/
cp ../axcl_studio/server-backend/main.py rootfs/root/app/main.py
cp ../axcl_studio/server-backend/yolov5_runner.py rootfs/root/app/yolov5_runner.py

# Step 9: Final configuration and mount
cp sources.list rootfs/etc/apt/sources.list
cp inside_install.sh rootfs/
sudo ./ch-mount.sh -m rootfs/


# Step 10: Run installation inside the chroot (execute `inside_install.sh`)
cat <<EOF | sudo chroot rootfs/
/inside_install.sh
EOF

# Step 11: Exit the chroot, unmount pseudo-filesystems
sudo ./ch-mount.sh -u rootfs/

# Step 12: Calculate and print rootfs usage percentage and CMM pool config
ROOTFS_SIZE_BYTES=$(sudo du -sb rootfs/ | awk '{print $1}')
SIZE_BYTES=$((NUM * 1024 * 1024))
USAGE_PERCENT=$((ROOTFS_SIZE_BYTES * 100 / SIZE_BYTES))
echo "Rootfs usage: $USAGE_PERCENT% ($ROOTFS_SIZE_BYTES bytes used out of $SIZE_BYTES bytes)"

FIXED_MB_OS=1024
FIRST_ADDR=$((0x100000000 + (NUM + FIXED_MB_OS) * 0x100000))
FIRST_HEX=$(printf "0x%x" $FIRST_ADDR)
SECOND_MB=$((8192 - FIXED_MB_OS - NUM))
echo "Calculated CMM pool config: anonymous,0,$FIRST_HEX,${SECOND_MB}M"

# Step 13: Package rootfs into an ext4 image
sudo ./make_ext4fs -l $SIZE rootfs.ext4 rootfs/

echo "--------------------------------------------------------"
echo "Customization complete! Created rootfs.ext4 with size $SIZE"
echo "--------------------------------------------------------"