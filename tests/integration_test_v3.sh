#!/bin/bash
# kbase 集成测试脚本 v3
# 测试多种关键词和配置组合

set -e

PROJECT_DIR="/home/lan/workspace/test/search/inc"
RESULTS_DIR="/tmp/kbase-integration-results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$RESULTS_DIR"

# 初始化CSV
echo "keyword,max_results,timeout,elapsed_sec,total_count,cache_count,has_real_error" > "$RESULTS_DIR/results_${TIMESTAMP}.csv"

echo "========================================"
echo "kbase 集成测试 v3"
echo "时间: $TIMESTAMP"
echo "========================================"

# 测试函数
test_search() {
    local keyword="$1"
    local max_results="$2"
    local timeout="$3"
    local extra_opts="$4"
    local should_clean="$5"  # YES 或 NO

    local cmd="uv run kbase $extra_opts \"$keyword\""

    echo "测试: $cmd"

    # 根据参数决定是否清理缓存
    if [ "$should_clean" = "YES" ]; then
        rm -rf ~/.kbase/
    fi

    local start_time=$(date +%s.%N)
    local exit_code=0
    local output=$(eval "$cmd" 2>&1) || exit_code=1
    local end_time=$(date +%s.%N)
    local elapsed=$(echo "$end_time - $start_time" | bc)

    # 解析结果数量
    local total_count=$(echo "$output" | grep "总计:" | grep -oE '[0-9]+' || echo "0")

    # 检查缓存命中数量
    local cache_count=$(echo "$output" | grep "缓存结果" | grep -oE '\([0-9]+条\)' | grep -oE '[0-9]+' || echo "0")

    # 使用退出码检测错误
    local has_real_error=""
    if [ "$exit_code" -ne 0 ]; then
        has_real_error="YES"
    else
        has_real_error="NO"
    fi

    printf "  耗时: %.2fs | 结果: %s条 | 缓存: %s条 | 错误: %s\n" "$elapsed" "$total_count" "$cache_count" "$has_real_error"

    # 记录到文件
    echo "${keyword},${max_results},${timeout},${elapsed},${total_count},${cache_count},${has_real_error}" >> "$RESULTS_DIR/results_${TIMESTAMP}.csv"
}

echo ""
echo "=== 第一轮: 中文关键词（清理缓存） ==="
echo ""

test_search "伊朗今日局势" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "中国股市" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "北京天气" 3 15 "--max-results 3 --timeout 15" "YES"
test_search "人工智能发展" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "机器学习入门" 5 30 "--max-results 5 --timeout 30" "YES"

echo ""
echo "=== 第二轮: 英文关键词（清理缓存） ==="
echo ""

test_search "python async" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "docker compose" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "kubernetes pod" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "typescript generics" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "react hooks tutorial" 5 30 "--max-results 5 --timeout 30" "YES"

echo ""
echo "=== 第三轮: max_results 配置测试（清理缓存） ==="
echo ""

test_search "python" 3 30 "--max-results 3 --timeout 30" "YES"
test_search "python" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "python" 10 60 "--max-results 10 --timeout 60" "YES"

echo ""
echo "=== 第四轮: timeout 配置测试（清理缓存） ==="
echo ""

test_search "rust" 5 10 "--max-results 5 --timeout 10" "YES"
test_search "rust" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "rust" 5 60 "--max-results 5 --timeout 60" "YES"

echo ""
echo "=== 第五轮: 输出格式测试（清理缓存） ==="
echo ""

test_search "git branch" 5 30 "--max-results 5 --timeout 30 --format markdown" "YES"
test_search "git branch" 5 30 "--max-results 5 --timeout 30 --format path" "YES"

echo ""
echo "=== 第六轮: 时间范围测试（清理缓存） ==="
echo ""

test_search "AI technology" 5 30 "--max-results 5 --timeout 30 --time-range day" "YES"
test_search "AI technology" 5 30 "--max-results 5 --timeout 30 --time-range week" "YES"
test_search "AI technology" 5 30 "--max-results 5 --timeout 30 --time-range month" "YES"

echo ""
echo "=== 第七轮: 缓存命中测试（不清理缓存） ==="
echo ""

# 建立缓存（清理后搜索）
echo "建立缓存..."
test_search "cache_test_keyword" 5 30 "--max-results 5 --timeout 30" "YES"

# 缓存命中测试（不清理）
echo "缓存命中（精确匹配）..."
test_search "cache_test_keyword" 5 30 "--max-results 5 --timeout 30" "NO"

# 部分匹配测试（不清理）
echo "缓存命中（部分匹配）..."
test_search "cache_test" 5 30 "--max-results 5 --timeout 30" "NO"

# 强制网络搜索（不清理）
echo "强制网络搜索..."
test_search "cache_test_keyword" 5 30 "--max-results 5 --timeout 30 --no-cache" "NO"

# 仅缓存搜索（不清理）
echo "仅缓存搜索..."
test_search "cache_test_keyword" 5 30 "--max-results 5 --timeout 30 --only-cache" "NO"

echo ""
echo "=== 第八轮: 技术文档搜索（清理缓存） ==="
echo ""

test_search "fastapi tutorial" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "pytest fixture" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "numpy array operations" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "pandas dataframe merge" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "linux systemd service" 5 30 "--max-results 5 --timeout 30" "YES"

echo ""
echo "=== 第九轮: 混合关键词（清理缓存） ==="
echo ""

test_search "API REST GraphQL" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "database optimization" 5 30 "--max-results 5 --timeout 30" "YES"
test_search "web security best practices" 5 30 "--max-results 5 --timeout 30" "YES"

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
cache_results=$(awk -F',' 'NR>1 {sum+= $6} END {print sum+0}' "$RESULTS_DIR/results_${TIMESTAMP}.csv")
errors=$(awk -F',' 'NR>1 && $7=="YES" {count++} END {print count+0}' "$RESULTS_DIR/results_${TIMESTAMP}.csv")

echo "总测试数: $total_tests"
echo "平均耗时: ${avg_time}s"
echo "最大耗时: ${max_time}s"
echo "最小耗时: ${min_time}s"
echo "总结果数: $total_results"
echo "缓存结果数: $cache_results"
echo "真正错误数: $errors"

# 分类别统计
echo ""
echo "=== 分类别统计 ==="

echo "中文关键词平均耗时:"
awk -F',' 'NR>1 && NR<=5 {sum+= $4; count++} END {if(count>0) printf "%.2fs\n", sum/count}' "$RESULTS_DIR/results_${TIMESTAMP}.csv"

echo "英文关键词平均耗时:"
awk -F',' 'NR>1 && NR>5 && NR<=10 {sum+= $4; count++} END {if(count>0) printf "%.2fs\n", sum/count}' "$RESULTS_DIR/results_${TIMESTAMP}.csv"

echo "max_results=3 耗时:"
awk -F',' 'NR>1 && $2=="3" {sum+= $4; count++} END {if(count>0) printf "%.2fs\n", sum/count}' "$RESULTS_DIR/results_${TIMESTAMP}.csv"

echo "max_results=5 耗时:"
awk -F',' 'NR>1 && $2=="5" {sum+= $4; count++} END {if(count>0) printf "%.2fs\n", sum/count}' "$RESULTS_DIR/results_${TIMESTAMP}.csv"

echo "max_results=10 耗时:"
awk -F',' 'NR>1 && $2=="10" {sum+= $4; count++} END {if(count>0) printf "%.2fs\n", sum/count}' "$RESULTS_DIR/results_${TIMESTAMP}.csv"

echo ""
echo "=== CSV 数据 ==="
column -t -s',' "$RESULTS_DIR/results_${TIMESTAMP}.csv"