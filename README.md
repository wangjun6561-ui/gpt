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
1. **方向识别修正**
   - 优先使用 `posSide` (`long/short`)；
   - `net` 或空值时，使用 `pos` 正负兜底推断方向，减少误判。

2. **默认单币种 + 点击展开全部持仓**
   - 默认显示一个主仓；
   - 点击按钮后可查看当前全部持仓明细。

3. **方向底色一眼可见**
   - 空单卡片：绿色底；
   - 多单卡片：红色底；
   - 空仓卡片：中性深色。

4. **按保证金金额排序**
   - 博主列表按“主仓保证金”从高到低排序（空仓在后）；
   - 单个博主展开后的持仓也按保证金降序排列。

5. **性能优化逻辑**
   - 不再每轮都拉持仓；
   - 每轮仅轮询 trade-records；
   - 仅发生新交易时刷新对应博主持仓。

6. **独立 HTML 模板**
   - 页面单独放在 `templates/dashboard.html`，后续前端调整更方便；
   - 使用 Vue3 CDN 做轻量交互（无需本地打包）。

## 4. 配置
- `config.example.json` 中配置 `traders`、`okx.contract_values`、通知参数等。
- `debug: true` 可输出关键调试日志。
