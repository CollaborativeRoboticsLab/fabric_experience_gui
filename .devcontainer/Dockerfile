FROM osrf/ros:jazzy-desktop

RUN apt-get update && apt-get install -y --no-install-recommends \
    git sudo python3-colcon-common-extensions python3-vcstool python3-rosdep \
    python3-pytest python3-numpy python3-matplotlib \
    && rm -rf /var/lib/apt/lists/* \
    && (id -u ubuntu >/dev/null 2>&1 || useradd -m -s /bin/bash ubuntu) \
    && echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/fabric-gui \
    && chmod 0440 /etc/sudoers.d/fabric-gui