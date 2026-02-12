# Telegram-115Bot v3.4.0
## 本次更新内容：
- 支持生成302的strm文件，不占本地上传（需要单独部署go-emby2openlist）
- 增加目录缓存，减少API请求。尽量不要在运行bot后更新相关目录（修改/删除/重命名），如果必须更新，更新后请务必重启bot
- 限制bot请求115的qps <= 2 如果你同时也用CD2 bot + CD2 的qps不应超过 5
- 限制每日请求次数，普通VIP每日请求<=9500, 永久VIP每日请求<=14250
- 转发视频支持重命名
- 在离线数量比较小的情况下，删除已完成只删除本次的离线任务，避免影响其他同时离线的任务
- 其他优化

***
本次更新涉及配置文件变更，请自行修改

create_strm 变更为 strm_mode，可选值见配置说明

添加 openlist_root，配置Openlist挂载的115根目录
302模式
```yaml
# 可选值：
# - strm_302        # strm + OpenList 302（推荐, 需要自己部署go-emby2openlist）
# - strm_local       # 只生成本地strm，不走 302（与原来保持一致）
# - disable         # 禁用strm生成功能
strm_mode: strm_302
# strm文件存放路径(Emby挂载路径)
strm_root: /media/115
# OpenList 115挂载根路径(302用)
openlist_root: /115
# CD2 115根目录
mount_root: /CloudNAS/115
```

有任何使用问题欢迎群内讨论~

[TG讨论群](https://t.me/+FTPNla_7SCc3ZWVl)







