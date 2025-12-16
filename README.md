# axcl_forge
此项目由两大模块组成， `axcl_studio` 和 `rootfs_custom` 。

## 项目简介

`axcl_studio`是AXCL的增强工具包，专为算力卡设计。它基于前后端分离设计，提供Web界面，帮助用户管理和操作算力卡，并进行远程监控。主要功能如下：

- **状态总览**：实时显示算力卡的系统信息，如CPU使用率、内存、温度和NPU状态。
- **文件传输**：支持上传和下载文件到算力卡，便于模型和数据的管理。
- **虚拟终端**：提供SSH-like的终端界面，直接在浏览器中远程操作算力卡。
- **Demo (YOLOv5s)**：内置YOLOv5s模型演示，展示算力卡的AI推理能力。

`rootfs_custom`是专为算力卡设计的rootfs定制工具包。它基于原始的算力卡rootfs.ext4，通过自动化脚本定制，预装必要的组件，使算力卡初步具备一个小型片上服务器的能力，做到开卡即用。主要功能如下：

- **python(pip)支持**：嵌入Python环境和依赖，可用于AI推理后的数据处理，依赖包可扩展。
- **APT支持**：嵌入APT软件包管理系统，支持安装和更新软件包，便于进一步扩展。
- **开发模式**：允许远程SSH访问和应用部署，便于调试和迭代。
- **axcl_studio集成**：集成axcl_studio，提供AXCL增强工具包使用体验。


## 项目结构

```
axcl_card_rootfs/
├── axcl_studio/            # axcl_studio
│   ├── server-backend/     # FastAPI后端
│   └── web-frontend/       # Vue.js前端
├── rootfs_custom/          # rootfs定制工具
│   ├── custom_enter.sh     # 主定制脚本
│   └── ...
├── example/                # example
│   ├── *.deb               # 示例驱动包
│   ├── README.md           # 示例使用说明
│   └── ...
└── README.md
```

## 快速开始

1. 编译axcl_studio前端。
2. 准备原始rootfs.ext4，运行脚本，定制新rootfs.ext4。
3. 将新生成的rootfs.ext4用于算力卡驱动打包.

###  AXCL Studio

#### 编译前端

1. 进入前端目录：
   ```bash
   cd axcl_studio/web-frontend
   ```

2. 安装依赖：
   ```bash
   npm install
   ```

3. 编译前端：
   ```bash
   npm run build
   ```
   编译后的文件将在 `dist/` 目录中。

### ROOTFS CUSTOM

#### 准备工作

1. 安装rsyn：
   ```bash
   sudo apt-get update
   sudo apt-get install rsync
   ```

2. 确认 `axcl_studio` 已经编译：已生成 `axcl_studio/web-frontend/dist/` 目录。

3. 准备 `rootfs_origin.ext4` 文件：这是算力卡原始的rootfs镜像。  
如果您有SDK，那么编译card工程后位于build/out/AX650_card/images/rootfs.ext4。  
请确保该文件被拷贝到 `rootfs_custom/` 目录下，并被重命名为`rootfs_origin.ext4`。

#### 执行定制

1. 进入rootfs_custom目录：
   ```bash
   cd rootfs_custom
   ```

2. 运行定制脚本：
   ```bash
   ./custom_rootfs.sh
   ```

### 重新打包算力卡驱动

定制完成得到 `rootfs.ext4` 文件，可用于生成新的驱动包。  
将其替换掉SDK目录的 `build/out/AX650_card/images/rootfs.ext4`。  
然后执行 `make p=AX650_card axp` 重新进行驱动打包。

> **⚠️ 重要提醒**：因为rootfs.ext4的大小有更改，打包驱动前请务必同步更改ramdisk大小和CMM配置，以确保系统正常运行。

#### 使用示例

[example目录](example/) 有示例驱动包。  
使用示例可参考 [Usage](example/README.md) 。