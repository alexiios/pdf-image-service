# PDF Image-Only Converter

一个很小的PDF转换网页工具。上传PDF后，服务会把每一页渲染成PNG图片，再重新合成为新的PDF。

## 本地运行

前提：你已经安装 Docker。

```bash
docker build -t pdf-image-service .
docker run --rm -p 10000:10000 -e ACCESS_PASSWORD=123456 pdf-image-service
```

打开：

```text
http://localhost:10000
```

## 部署到 Render

1. 新建一个 GitHub 仓库，比如 `pdf-image-service`
2. 把本项目里的所有文件上传到仓库根目录
3. 打开 Render Dashboard
4. 选择 New > Web Service
5. 连接 GitHub 仓库
6. Language 选择 Docker
7. Instance Type 先选 Free
8. Advanced 里添加环境变量

建议添加：

```text
ACCESS_PASSWORD=你自己设置的密码
MAX_UPLOAD_MB=80
CONVERT_TIMEOUT_SECONDS=900
```

创建服务后，Render会自动构建并部署。部署完成后，页面会有一个 `onrender.com` 地址。

## 说明

- `180 DPI`：普通，文件较小
- `220 DPI`：清晰，推荐
- `300 DPI`：高清，文件较大

PDF转换会消耗CPU和临时磁盘。Render免费档适合测试和少量使用，不建议直接拿来处理很多大文件。
