#!/usr/bin/env python3
"""시장 지표를 공식 API에서 받아 data/market_auto.json 을 만든다.

- 한국은행 ECOS (환경변수 ECOS_KEY): 기준금리, 예금은행 주택담보대출 금리(신규취급), 국고채 3년
- 한국부동산원 R-ONE (환경변수 RONE_KEY): 주간 아파트 매매·전세 가격지수(서울·동대문구·광진구), 주간 매매수급동향(서울·동북권)

한쪽이 실패해도 다른 쪽은 저장한다. 실패한 부분은 errors 에 남긴다.
"""
import json, os, sys, time, datetime, urllib.request, urllib.parse

KST = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(KST)
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "market_auto.json")
ECOS_KEY = os.environ.get("ECOS_KEY", "").strip()
RONE_KEY = os.environ.get("RONE_KEY", "").strip()


def get_json(url):
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (realestate-daily)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = repr(e)
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(last)


# ---------------- 한국은행 ECOS ----------------
def ecos(stat, cycle, start, end, item):
    url = f"https://ecos.bok.or.kr/api/StatisticSearch/{ECOS_KEY}/json/kr/1/1000/{stat}/{cycle}/{start}/{end}/{item}"
    j = get_json(url)
    if "StatisticSearch" not in j:
        raise RuntimeError(f"ECOS {stat}/{item}: {json.dumps(j, ensure_ascii=False)[:200]}")
    rows = j["StatisticSearch"]["row"]
    def t(s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else f"{s[:4]}-{s[4:6]}"
    return [{"t": t(r["TIME"]), "v": float(r["DATA_VALUE"])} for r in rows if r.get("DATA_VALUE") not in (None, "")]


def fetch_ecos():
    m_start = (now - datetime.timedelta(days=760)).strftime("%Y%m")
    m_end = now.strftime("%Y%m")
    d_start = (now - datetime.timedelta(days=200)).strftime("%Y%m%d")
    d_end = now.strftime("%Y%m%d")
    out = {}
    out["baseRate"] = ecos("722Y001", "M", m_start, m_end, "0101000")
    daily = ecos("722Y001", "D", d_start, d_end, "0101000")
    if daily:
        out["baseRateLatest"] = daily[-1]
    out["mortgageRate"] = ecos("121Y006", "M", m_start, m_end, "BECBLA0302")
    ktb = ecos("817Y002", "D", d_start, d_end, "010200000")
    # 일별은 너무 많으니 주 1회 값만 남긴다 (마지막 값은 항상 포함)
    out["ktb3"] = [r for i, r in enumerate(ktb) if i % 5 == 0 or i == len(ktb) - 1]
    return out


# ---------------- 한국부동산원 R-ONE ----------------
RONE = "https://www.reb.or.kr/r-one/openapi/SttsApiTblData.do"
T_SALE = "T244183132827305"     # (주) 매매가격지수 (아파트)
T_JEONSE = "T247713133046872"   # (주) 전세가격지수 (아파트)
T_SUPPLY = "T248163133074619"   # (주) 매매수급동향 (아파트)
REGIONS = {"서울": 50008, "동대문구": 50049, "광진구": 50048}
SUPPLY_REGIONS = {"서울": 50008, "동북권": 50011}


def rone(table, cls, start_wk):
    q = urllib.parse.urlencode({"KEY": RONE_KEY, "Type": "json", "pIndex": 1, "pSize": 1000,
                                "STATBL_ID": table, "DTACYCLE_CD": "WK", "CLS_ID": cls,
                                "ITM_ID": 10001, "START_WRTTIME": start_wk})
    j = get_json(f"{RONE}?{q}")
    if "SttsApiTblData" not in j:
        raise RuntimeError(f"R-ONE {table}/{cls}: {json.dumps(j, ensure_ascii=False)[:200]}")
    rows = j["SttsApiTblData"][1]["row"]
    rows.sort(key=lambda r: r["WRTTIME_IDTFR_ID"])
    return [{"wk": r["WRTTIME_IDTFR_ID"], "date": r.get("WRTTIME_DESC") or r["WRTTIME_IDTFR_ID"], "v": float(r["DTA_VAL"])}
            for r in rows if r.get("DTA_VAL") is not None]


def with_change(series):
    out = []
    for i, r in enumerate(series):
        chg = None if i == 0 else round((r["v"] / series[i - 1]["v"] - 1) * 100, 2)
        out.append({"date": r["date"], "idx": round(r["v"], 3), "chg": chg})
    return out[1:]


def fetch_rone():
    y, w, _ = (now - datetime.timedelta(days=420)).isocalendar()
    start = f"{y}{w:02d}"
    out = {"sale": {}, "jeonse": {}, "supply": {}}
    for name, cls in REGIONS.items():
        out["sale"][name] = with_change(rone(T_SALE, cls, start))
        out["jeonse"][name] = with_change(rone(T_JEONSE, cls, start))
    for name, cls in SUPPLY_REGIONS.items():
        out["supply"][name] = [{"date": r["date"], "v": round(r["v"], 1)} for r in rone(T_SUPPLY, cls, start)]
    return out


def main():
    try:
        prev = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        prev = {}
    result = {"updatedAt": now.isoformat(timespec="minutes"), "errors": []}
    for name, key, fn in [("ecos", ECOS_KEY, fetch_ecos), ("rone", RONE_KEY, fetch_rone)]:
        if not key:
            result["errors"].append(f"{name}: 인증키 없음")
            if name in prev:
                result[name] = prev[name]
            continue
        try:
            result[name] = fn()
            print(name, "ok")
        except Exception as e:
            print(name, "실패:", e, file=sys.stderr)
            result["errors"].append(f"{name}: {e}"[:300])
            if name in prev:
                result[name] = prev[name]  # 실패하면 이전 값 유지
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    if "ecos" not in result and "rone" not in result:
        sys.exit("ECOS, R-ONE 모두 실패")


if __name__ == "__main__":
    main()
