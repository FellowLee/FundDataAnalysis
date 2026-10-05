import requests
import pandas as pd
import json
import time
import re
import os



def fetch_fund_history(fund_code="377530", max_pages=2):
    """
    爬取指定基金的历史净值数据
    :param fund_code: 基金代码
    :param max_pages: 最大翻页次数，防止死循环
    :return: DataFrame
    """
    df_list = []
    
    headers = {
        "Referer": "https://fundf10.eastmoney.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    print(f"开始爬取基金 {fund_code} 的历史数据...")

    for index in range(1, max_pages + 1):
        # 使用纯JSON接口
        url = f"https://api.fund.eastmoney.com/f10/lsjz?fundCode={fund_code}&pageIndex={index}&pageSize=20&startDate=&endDate="
        
        try:
            # 增加超时设置，防止请求挂起
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()  # 如果状态码不是200，抛出异常
            data = resp.json()
            
            # 检查数据结构
            if data.get("Data") and data["Data"].get("LSJZList"):
                lsjz_list = data["Data"]["LSJZList"]
                
                if not lsjz_list:
                    print(f"第{index}页: 数据为空，停止翻页")
                    break
                
                df = pd.DataFrame(lsjz_list)
                df_list.append(df)

                

                print(f"第{index}页: 获取到 {len(df)} 条记录")
                
                # 如果返回的数据少于 pageSize (20)，说明已经是最后一页
                if len(lsjz_list) < 20:
                    print("已到达最后一页")
                    break
            else:
                print(f"第{index}页: 响应格式异常，停止翻页")
                break
                
        except requests.exceptions.RequestException as e:
            print(f"请求出错: {e}")
            break
        except Exception as e:
            print(f"处理数据时出错: {e}")
            break
        
        # 礼貌爬取，避免频率过高被封IP
        time.sleep(0.5)


    if not df_list:
        print("未获取到任何数据")
        return pd.DataFrame()

    # 合并数据
    df_data = pd.concat(df_list, ignore_index=True)

    # 数据清洗与类型转换
    # 将数值列转换为 float，处理可能的空值或特殊字符
    numeric_cols = ["DWJZ", "LJJZ", "JZZZL"]
    for col in numeric_cols:
        if col in df_data.columns:
            df_data[col] = pd.to_numeric(df_data[col], errors='coerce')

    # 重命名列
    column_rename = {
        "FSRQ": "日期", 
        "DWJZ": "单位净值", 
        "LJJZ": "累计净值",
        "JZZZL": "日增长率(%)", 
        "SGZT": "申购状态", 
        "SHZT": "赎回状态"
    }



    # 只重命名存在的列，避免 KeyError
    existing_cols_to_rename = {k: v for k, v in column_rename.items() if k in df_data.columns}
    df_data = df_data.rename(columns=existing_cols_to_rename)
    
    # ========== 优化1： 新增：将"日增长率(%)"列数据以百分数格式显示 ======
    if "日增长率(%)" in df_data.columns:
        df_data["日增长率(%)"] = df_data["日增长率(%)"].apply(
            lambda x: f"{x:.2f}%" if pd.notna(x) else ""
        )
    # =================================================================    
    

    # ========== 优化2：只保留需要的4列，列排序不变 =============
    keep_cols = ["日期", "单位净值", "累计净值", "日增长率(%)"]
    existing_keep_cols = [col for col in keep_cols if col in df_data.columns]
    df_data = df_data[existing_keep_cols]
    # ========================================================

    #print(df_data)

    # 按日期降序排列
    if "日期" in df_data.columns:
        df_data = df_data.sort_values("日期", ascending=False).reset_index(drop=True)

    return df_data   

def fetch_and_save_fund_info(fund_code):
    """
    根据基金代码从东方财富网获取基金信息并保存为CSV
    :param fund_code: 基金代码 (str)
    """
    name_url = "https://fund.eastmoney.com/js/fundcode_search.js?v=20260924150816"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://fund.eastmoney.com/"
    }
    
    try:
        # 1. 发起网络请求
        response = requests.get(name_url, headers=headers, timeout=10)
        response.raise_for_status()
        response_text = response.text
        
        # 2. 使用正则表达式提取 var r = [...]; 中的数组部分
        matches = re.findall(r'var r = (\[.*?\]);', response_text, re.DOTALL)
        if not matches:
            raise IndexError("未能从响应文本中匹配到基金数据数组")
            
        json_str = matches[0]
        
        # 3. 基础清洗：替换中文引号、去除换行和注释等
        json_str = json_str.replace('“', '"').replace('”', '"')
        json_str = json_str.replace('‘', "'").replace('’', "'")
        json_str = json_str.replace('\n', '').replace('\r', '')
        # 去除可能存在的JS注释 (简单处理)
        json_str = re.sub(r'//.*', '', json_str)
        
        # 4. 安全解析为Python列表
        try:
            fund_data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON数据解析失败，数据格式可能异常: {e}")
            
        # 5. 构造 pandas.DataFrame
        columns = ["code", "nav", "name", "type", "company"]
        df = pd.DataFrame(fund_data, columns=columns)
        
        # 6. 筛选匹配的记录
        matched_df = df[df['code'] == fund_code]
        
        # 7. 根据匹配结果执行输出或保存
        if not matched_df.empty:
            fund_name = matched_df.iloc[0]['name']
            print(f"查找成功:基金 {fund_code} 的名称是{fund_name}")

            return fund_name
        else:
            print("查找失败。")
            
    except (requests.RequestException, json.JSONDecodeError, IndexError, ValueError) as e:
        print(f"请求或解析失败：{e}")

if __name__ == "__main__":
    
    # 抓取基金代码，页数
    fund_code = "002910"
    pages = 1

    fund_name = fetch_and_save_fund_info(fund_code)

    df_result = fetch_fund_history(fund_code=fund_code,max_pages=pages)

    if not df_result.empty:

        filename = f"{fund_name}({fund_code}).csv"

        # encoding='utf-8-sig' 确保 Excel 打开中文不乱码
        df_result.to_csv(filename, index=False, encoding="utf-8-sig")

        print(f"\n成功! 总计 {len(df_result)} 条记录，已保存至: {filename}")

        print(df_result.head()) # 打印前几行预览
    else:
        print("未能生成数据文件。")