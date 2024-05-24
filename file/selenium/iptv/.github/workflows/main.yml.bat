name: 直播源g


on:
  workflow_dispatch:
  schedule:
    - cron: '0 9 * * *'

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: 检出代码
        uses: actions/checkout@v2
    
      - name: 设置 Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.x

      - name: 安装依赖
        run: pip install selenium requests futures eventlet

      - name: Run itv
        run: python ${{ github.workspace }}/py/itv.py

      - name: 运行直播源采集脚本
        run: |
          nohup python ${{ github.workspace }}/py/cctv.py &
          nohup python ${{ github.workspace }}/py/weishi.py &
          nohup python ${{ github.workspace }}/py/qita.py &
          wait

      - name: 合并文件
        run: python ${{ github.workspace }}/py/hebing.py
        
      - name: 提交更改
        run: |
          git config --local user.email "csszue@gmail.com"  # 设置 Git 用户邮箱
          git config --local user.name "MemoryCollection"  # 设置 Git 用户名
          git add tv/*  # 添加 tv/ 目录下的所有文件

          git commit -m "$(TZ=Asia/Shanghai date +'%Y-%m-%d %H:%M:%S') ：采集"
          #git pull --rebase
          git push -f
