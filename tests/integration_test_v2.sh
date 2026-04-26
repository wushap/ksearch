#!/bin/bash
# ksearch 集成测试脚本 v2
# 测试多种关键词和配置组合

set -e

PROJECT_DIR="/home/lan/workspace/test/search/inc"
RESULTS_DIR="/tmp/ksearch-integration-results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$RESULTS_DIR"

echo "========================================"
echo "ksearch 集成测试 v2"
echo "时间: $TIMESTAMP"
echo "========================================"

# 清理缓存
cleanup() {
    rm -rf ~/.ksearch/
}

# 测试函数
test_search() {
    local keyword="$1"
    local max_results="$2"
    local timeout="$3"
    local extra_opts="$4"

    local cmd="uv run ksearch $extra_opts \"$keyword\""

    echo "测试: $cmd"
    cleanup

    local start_time=$(date +%s.%N)
    local output=$(eval "$cmd" 2>&1 || true)
    local end_time=$(date +%s.%N)
    local elapsed=$(echo "$end_time - $start_time" | bc)

    # 解析结果数量
    local total_count=$(echo "$output" | grep "总计:" | grep -oE '[0-9]+' || echo "0")
    local has_error=""
    if echo "$output" | grep -q "Error"; then
        has_error="YES"
    else
        has_error="NO"
    fi

    # 检查缓存命中
    local cache_hit=""
    if echo "$output" | grep -q "缓存结果"; then
        cache_hit="YES"
    else
        cache_hit="NO"
    fi

    printf "  耗时: %.2fs | 结果: %s条 | 缓存: %s | 错误: %s\n" "$elapsed" "$total_count" "$cache_hit" "$has_error"

    # 记录到文件
    echo "${keyword},${max_results},${timeout},${elapsed},${total_count},${cache_hit},${has_error}" >> "$RESULTS_DIR/results_${TIMESTAMP}.csv"
}

# 初始化CSV
echo "keyword,max_results,timeout,elapsed_sec,total_count,cache_hit,has_error" > "$RESULTS_DIR/results_${TIMESTAMP}.csv"

echo ""
echo "=== 第一轮: 中文关键词 ==="
echo ""

test_search "伊朗今日局势" 5 30 "--max-results 5 --timeout 30"
test_search "中国股市" 5 30 "--max-results 5 --timeout 30"
test_search "北京天气" 3 15 "--max-results 3 --timeout 15"
test_search "人工智能发展" 5 30 "--max-results 5 --timeout 30"
test_search "机器学习入门" 5 30 "--max-results 5 --timeout 30"

echo ""
echo "=== 第二轮: 英文关键词 ==="
echo ""

test_search "python async" 5 30 "--max-results 5 --timeout 30"
test_search "docker compose" 5 30 "--max-results 5 --timeout 30"
test_search "kubernetes pod" 5 30 "--max-results 5 --timeout 30"
test_search "typescript generics" 5 30 "--max-results 5 --timeout 30"
test_search "react hooks tutorial" 5 30 "--max-results 5 --timeout 30"

echo ""
echo "=== 第三轮: max_results 配置测试 ==="
echo ""

test_search "python" 3 30 "--max-results 3 --timeout 30"
test_search "python" 5 30 "--max-results 5 --timeout 30"
test_search "python" 10 60 "--max-results 10 --timeout 60"

echo ""
echo "=== 第四轮: timeout 配置测试 ==="
echo ""

test_search "rust" 5 10 "--max-results 5 --timeout 10"
test_search "rust" 5 30 "--max-results 5 --timeout 30"
test_search "rust" 5 60 "--max-results 5 --timeout 60"

echo ""
echo "=== 第五轮: 输出格式测试 ==="
echo ""

test_search "git branch" 5 30 "--max-results 5 --timeout 30 --format markdown"
test_search "git branch" 5 30 "--max-results 5 --timeout 30 --format path"

echo ""
echo "=== 第六轮: 时间范围测试 ==="
echo ""

test_search "AI technology" 5 30 "--max-results 5 --timeout 30 --time-range day"
test_search "AI technology" 5 30 "--max-results 5 --timeout 30 --time-range week"
test_search "AI technology" 5 30 "--max-results 5 --timeout 30 --time-range month"

echo ""
echo "=== 第七轮: 缓存命中测试 ==="
echo ""

# 先搜索建立缓存
echo "建立缓存..."
test_search "test_cache_hit" 5 30 "--max-results 5 --timeout 30"

# 再次搜索（应命中缓存）
echo "缓存命中测试..."
test_search "test_cache_hit" 5 30 "--max-results 5 --timeout 30"

# 部分匹配测试
test_search "test_cache" 5 30 "--max-results 5 --timeout 30"

# 强制网络搜索
test_search "test_cache_hit" 5 30 "--max-results 5 --timeout 30 --no-cache"

# 仅缓存搜索
test_search "test_cache_hit" 5 30 "--max-results 5 --timeout 30 --only-cache"

echo ""
echo "=== 第八轮: 技术文档搜索 ==="
echo ""

test_search "fastapi tutorial" 5 30 "--max-results 5 --timeout 30"
test_search "pytest fixture" 5 30 "--max-results 5 --timeout 30"
test_search "numpy array operations" 5 30 "--max-results 5 --timeout 30"
test_search "pandas dataframe merge" 5 30 "--max-results 5 --timeout 30"
test_search "linux systemd service" 5 30 "--max-results 5 --timeout 30"

echo ""
echo "=== 第九轮: 混合关键词 ==="
echo ""

test_search "API REST GraphQL" 5 30 "--max-results 5 --timeout 30"
test_search "database optimization" 5 30 "--max-results 5 --timeout 30"
test_search "web security best practices" 5 30 "--max-results 5 --timeout 30"

echo ""
echo "========================================"
echo "测试完成"
echo "========================================"

# 统计结果
echo ""
echo "=== 结果统计 ==="
echo ""

total_tests=$(wc -l < "$RESULTS_DIR/results_${TIMESTAMP}.csv")
total_tests=$((total_tests - 1))

avg_time=$(awk -F',' 'NR>1 {sum+= $4; count++} END {if(count>0) printf "%.2f", sum/count}' "$RESULTS_DIR/results_${TIMESTAMP}.csv")
max_time=$(awk -F',' 'NR>1 {if($4>max || NR==2) max=$4} END {printf "%.2f", max}' "$RESULTS_DIR/results_${TIMESTAMP}.csv")
min_time=$(awk -F',' 'NR>1 {if($4<min || NR==2) min=$4} END {printf "%.2f", min}' "$RESULTS_DIR/results_${TIMESTAMP}.csv")

total_results=$(awk -F',' 'NR>1 {sum+= $5} END {print sum+0}' "$RESULTS_DIR/results_${TIMESTAMP}.csv")
cache_hits=$(awk -F',' 'NR>1 && $6=="YES" {count++} END {print count+0}' "$RESULTS_DIR/results_${TIMESTAMP}.csv")
errors=$(awk -F',' 'NR>1 && $7=="YES" {count++} END {print count+0}' "$RESULTS_DIR/results_${TIMESTAMP}.csv")

echo "总测试数: $total_tests"
echo "平均耗时: ${avg_time}s"
echo "最大耗时: ${max_time}s"
echo "最小耗时: ${min_time}s"
echo "总结果数: $total_results"
echo "缓存命中: $cache_hits 次"
echo "错误数: $errors"

echo ""
echo "=== CSV 数据 ==="
column -t -s',' "$RESULTS_DIR/results_${TIMESTAMP}.csv"