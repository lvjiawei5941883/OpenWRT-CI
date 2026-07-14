#!/bin/bash
# SPDX-License-Identifier: MIT
# 老板的私有软件包 —— 你在 Scripts/Packages.sh 里额外加的包都放这里
# 这个文件不会被 Sync-Upstream 覆盖，永远安全

# 示例：你目前在 Packages.sh 末尾额外加了这两个
UPDATE_PACKAGE "lucky" "gdy666/luci-app-lucky" "main"
UPDATE_PACKAGE "adguardhome" "TanZhiwen2001/luci-app-adguardhome" "main"

# 以后要加新包直接往下面写，格式：
# UPDATE_PACKAGE "包名" "GitHub仓库" "分支" "特殊选项" "自定义名称列表"
