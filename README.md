# OKX 带单员实时监控（Flask + 独立前端模板）

本项目用于监控多个 OKX 带单博主：
- 启动时拉取当前持仓；
- 后续定时仅拉取交易记录；
- 仅当检测到交易变化时，再刷新该博主持仓；
- 页面默认展示单一优先币种（ETH/BTC/SOL），支持点击展开全部持仓；
- 支持 Server酱与邮件通知。

## 1. 环境
- Python 3.9
- Flask（轻量后端框架）

## 2. 运行
```bash
pip install -r requirements.txt
cp config.example.json config.json
python app.py
```
访问：`http://127.0.0.1:8080`

## 3. 主要特性
1. **请求重试与缓冲**
   - 每次接口请求后随机暂停 `0.3~0.5s`；
   - 失败自动最多重试 3 次（重试间隔同样暂停）。
   - 请求头含中文环境字段（`accept-language` / `x-locale` / `x-utc` / `x-zkdex-env`）。

2. **方向识别修正**
   - 优先使用 `posSide` (`long/short`)；
   - `net` 或空值时，使用 `pos` 正负兜底推断方向，减少误判。

3. **默认单币种 + 点击展开全部持仓**
   - 默认显示一个主仓；
   - 点击按钮后可查看当前全部持仓明细。
   - 卡片展示标记价格。

4. **方向底色一眼可见**
   - 空单卡片：红色底；
   - 多单卡片：绿色底；
   - 空仓卡片：中性深色。

5. **按保证金金额排序**
   - 博主列表按“主仓保证金”从高到低排序（空仓在后）；
   - 单个博主展开后的持仓也按保证金降序排列。

6. **性能优化逻辑**
   - 交易监控循环：按 `interval_seconds` 轮询 trade-records；
   - 持仓实时循环：按 `okx.position_batch_interval_seconds` 分批刷新持仓；
   - 默认每 10s 刷新 3 个账户（轮询更新列表）。

7. **右上角排行筛选下拉**
   - 支持：配置、所有、综合排序、收益率、收益额、胜率、带单规模、当前跟单人数、跟单用户收益；
   - 选择“配置”会回到 config.json 交易员；选择“所有”会合并所有分类并去除配置交易员后展示；其他选项会拉取对应 follow-rank 临时带单员列表；
   - 仅替换内存中的展示列表，不改 `config` 和本地数据文件。

8. **独立 HTML 模板**
   - 页面单独放在 `templates/dashboard.html`，后续前端调整更方便；
   - 使用 Alpine.js CDN 做轻量交互（无需本地打包）；
   - 点击博主姓名可直达 OKX 主页。

9. **白天/夜色主题切换**
   - 页面右上角按钮可切换主题；
   - 自动记住上次选择。

10. **预估爆仓价兜底计算**
   - 若 OKX `liqPx` 缺失，则按保证金率和杠杆做近似估算；
   - 保证金率低于 100% 视为爆仓风险。

## 4. 配置
- `config.example.json` 中配置 `traders`、`okx.contract_values`、通知参数等。
- `okx.follow_rank_size`: 拉取 follow-rank 每页数量（默认 9）。
- `okx.follow_rank_pages`: 拉取 follow-rank 页数（默认 1）。
- `okx.position_batch_size`: 每批刷新账户数（默认 3）。
- `okx.position_batch_interval_seconds`: 批次刷新间隔秒数（默认 10）。
- `debug: true` 可输出关键调试日志。


## 5. 页面单位
- 价格/金额统一使用 `U`；
- 仓位张数使用 `张`。
