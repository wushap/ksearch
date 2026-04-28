#!/bin/bash
# kbase 集成测试脚本
# 测试多种关键词和配置组合

set -e

PROJECT_DIR="/home/lan/workspace/test/search/inc"
RESULTS_DIR="/tmp/kbase-integration-results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$RESULTS_DIR"

echo "========================================"
echo "kbase 集成测试"
echo "时间: $TIMESTAMP"
echo "========================================"

# 清理缓存
cleanup() {
    rm -rf ~/.kbase/
}

# 测试函数
test_search() {
    local keyword="$1"
    local max_results="$2"
    local timeout="$3"
    local format="$4"
    local time_range="$5"
    local extra_flags="$6"

    local cmd="uv run kbase"

    if [ -n "$max_results" ]; then
        cmd="$cmd --max-results $max_results"
    fi
    if [ -n "$timeout" ]; then
        cmd="$cmd --timeout $timeout"
    fi
    if [ -n "$format" ]; then
        cmd="$cmd --format $format"
    fi
    if [ -n "$time_range" ]; then
        cmd="$cmd --time-range $time_range"
    fi
    if [ -n "$extra_flags" ]; then
        cmd="$cmd $extra_flags"
    fi
    cmd="$cmd \"$keyword\""

    echo "测试: $cmd"

    cleanup

    local start_time=$(date +%s.%N)
    local output=$(eval "$cmd" 2>&1)
    local end_time=$(date +%s.%N)
    local elapsed=$(echo "$end_time - $start_time" | bc)

    # 解析结果
    local cache_count=$(echo "$output" | grep -oP '缓存结果 \(\K[0-9]+' || echo "0")
    local network_count=$(echo "$output" | grep -oP '网络搜索结果 \(\K[0-9]+' || echo "0")
    local total_count=$(echo "$output" | grep -oP '总计: \K[0-9]+' || echo "0")
    local has_error=$(echo "$output" | grep -c "Error" || echo "0")

    echo "  耗时: ${elapsed}s"
    echo "  缓存: ${cache_count}条, 网络: ${network_count}条, 总计: ${total_count}条"
    if [ "$has_error" -gt 0 ]; then
        echo "  错误: YES"
    fi
    echo ""

    # 记录到文件
    echo "$keyword,$max_results,$timeout,$format,$time_range,$elapsed,$cache_count,$network_count,$total_count,$has_error" >> "$RESULTS_DIR/results_$TIMESTAMP.csv"
}

# 初始化CSV
echo "keyword,max_results,timeout,format,time_range,elapsed_sec,cache_count,network_count,total_count,has_error" > "$RESULTS_DIR/results_$TIMESTAMP.csv"

echo ""
echo "=== 第一轮: 中文关键词测试 ==="
echo ""

test_search "伊朗今日局势" 5 30 "markdown" "" ""
test_search "中国股市" 5 30 "markdown" "" ""
test_search "北京天气" 3 15 "markdown" "" ""
test_search "新冠病毒" 5 30 "markdown" "" ""
test_search "人工智能" 5 30 "markdown" "" ""

echo ""
echo "=== 第二轮: 英文关键词测试 ==="
echo ""

test_search "python async" 5 30 "markdown" "" ""
test_search "docker compose" 5 30 "markdown" "" ""
test_search "kubernetes pod" 5 30 "markdown" "" ""
test_search "typescript generics" 5 30 "markdown" "" ""
test_search "react hooks" 5 30 "markdown" "" ""

echo ""
echo "=== 第三轮: 配置组合测试 ==="
echo ""

# max_results 测试
test_search "python" 3 30 "markdown" "" ""
test_search "python" 5 30 "markdown" "" ""
test_search "python" 10 60 "markdown" "" ""

# timeout 测试
test_search "rust" 5 15 "markdown" "" ""
test_search "rust" 5 30 "markdown" "" ""
test_search "rust" 5 60 "markdown" "" ""

# format 测试
test_search "git" 5 30 "markdown" "" ""
test_search "git" 5 30 "path" "" ""

# time_range 测试
test_search "AI news" 5 30 "markdown" "day" ""
test_search "AI news" 5 30 "markdown" "week" ""
test_search "AI news" 5 30 "markdown" "month" ""

echo ""
echo "=== 第四轮: 缓存命中测试 ==="
echo ""

# 先搜索建立缓存
test_search "cache test keyword" 5 30 "markdown" "" ""
# 再次搜索应该命中缓存
test_search "cache test keyword" 5 30 "markdown" "" ""
# 部分匹配
test_search "cache" 5 30 "markdown" "" ""
# 强制网络搜索
test_search "cache test keyword" 5 30 "markdown" "" "--no-cache"
# 仅缓存搜索
test_search "cache test keyword" 5 30 "markdown" "" "--only-cache"

echo ""
echo "=== 第五轮: 技术文档搜索 ==="
echo ""

test_search "fastapi tutorial" 5 30 "markdown" "" ""
test_search "pytest fixture" 5 30 "markdown" "" ""
test_search "numpy array" 5 30 "markdown" "" ""
test_search "pandas dataframe" 5 30 "markdown" "" ""

echo ""
echo "========================================"
echo "测试完成"
echo "========================================"

# 统计结果
echo ""
echo "=== 结果统计 ==="
echo ""

total_tests=$(wc -l < "$RESULTS_DIR/results_$TIMESTAMP.csv")
total_tests=$((total_tests - 1))  # 减去header行

avg_time=$(awk -F',' 'NR>1 {sum+= $6; count++} END {if(count>0) printf "%.2f", sum/count}' "$RESULTS_DIR/results_$TIMESTAMP.csv")
max_time=$(awk -F',' 'NR>1 {if($6>max || NR==2) max=$6} END {printf "%.2f", max}' "$RESULTS_DIR/results_$TIMESTAMP.csv")
min_time=$(awk -F',' 'NR>1 {if($6<min || NR==2) min=$6} END {printf "%.2f", min}' "$RESULTS_DIR/results_$TIMESTAMP.csv")

success_count=$(awk -F',' 'NR>1 && $10==0 {count++} END {print count}' "$RESULTS_DIR/results_$TIMESTAMP.csv")
error_count=$(awk -F',' 'NR>1 && $10>0 {count++} END {print count+0}' "$RESULTS_DIR/results_$TIMESTAMP.csv")

total_cache=$(awk -F',' 'NR>1 {sum+= $7} END {print sum}' "$RESULTS_DIR/results_$TIMESTAMP.csv")
total_network=$(awk -F',' 'NR>1 {sum+= $8} END {print sum}' "$RESULTS_DIR/results_$TIMESTAMP.csv")

echo "总测试数: $total_tests"
echo "平均耗时: ${avg_time}s"
echo "最大耗时: ${max_time}s"
echo "最小耗时: ${min_time}s"
echo "成功/失败: $success_count/$error_count"
echo "缓存结果总数: $total_cache"
echo "网络结果总数: $total_network"

echo ""
echo "详细结果已保存到: $RESULTS_DIR/results_$TIMESTAMP.csv"

# 显示CSV内容
echo ""
echo "=== 完整测试数据 ==="
cat "$RESULTS_DIR/results_$TIMESTAMP.csv"