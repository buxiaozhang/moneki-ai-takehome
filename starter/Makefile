# 经营看板 + 问答服务
# 换数据或知识库：make rebuild DATA_DIR=/path/data KB_DIR=/path/kb

PY ?= .venv/bin/python
PORT ?= 8000
#: 评测脚本在上一层；题集路径相对仓库根目录。
EVAL ?= ../eval/run_eval.py
QUESTIONS ?= ../eval/public_questions.jsonl
#: 自建题集：公开题库之外补的那些（见 eval/my_questions.jsonl 的说明）。
MY_QUESTIONS ?= ../eval/my_questions.jsonl
export DATA_DIR KB_DIR VAR_DIR LLM_BASE_URL LLM_API_KEY LLM_MODEL

.PHONY: setup rebuild run test test-web eval eval-mine clean

setup:          ## 建虚拟环境并装依赖
	uv venv --python 3.12
	uv pip install --python $(PY) -r requirements.txt

rebuild:        ## 从 DATA_DIR 与 KB_DIR 重建清洗表和检索索引
	$(PY) -m kbqa.rebuild

run:            ## 启动服务，默认 8000 端口
	$(PY) -m uvicorn kbqa.server:app --host 127.0.0.1 --port $(PORT)

test:           ## 跑测试
	$(PY) -m pytest tests -q

test-web:       ## 跑前端 DOM 冒烟测试（需要 node 与 jsdom，缺了会自动跳过）
	node tests/web_smoke.js

# 评测即回归：每次改完代码都跑一遍，分数掉没掉一眼看得见。
# 需要服务已经在跑（另开一个终端 make run）。
# 一定要带 --out：不带就写到当前目录，会把 starter/ 弄脏。
eval:           ## 跑公开题库评测（对比满分看有没有掉分）
	$(PY) $(EVAL) --base-url http://localhost:$(PORT) --questions $(QUESTIONS) --out ../baselines/public

eval-mine:      ## 跑自建题集（公开题库之外的补充题）
	$(PY) $(EVAL) --base-url http://localhost:$(PORT) --questions $(MY_QUESTIONS) --out ../baselines/mine

clean:          ## 删掉清洗表
	rm -rf var
