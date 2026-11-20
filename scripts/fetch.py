#!/usr/bin/env python3
"""국토교통부 실거래가 API에서 관심 단지 데이터를 받아 data/*.json 을 만든다.

환경변수 DATA_GO_KR_KEY 에 공공데이터포털 인증키(Encoding 값, %2F 등이 들어간 것)를 넣는다.
표준 라이브러리만 쓴다.
"""
import json, os, sys, time, statistics, datetime, urllib.request, urllib.error, urllib.parse
import xml.etree.ElementTree as ET

KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
if not KEY:
    sys.exit("DATA_GO_KR_KEY 가 없습니다")
if "%" not in KEY:  # Decoding 키를 넣었으면 인코딩해 준다
    KEY = urllib.parse.quote(KEY, safe="")

BASE = "https://apis.data.go.kr/1613000"
OUT = os.path.join(os.path.dirname(__file__), "..", "data")

# 관심 단지: API 단지명 -> 화면 이름
TARGETS = {
    "장안힐스테이트": "장안힐스테이트",
    "래미안장안2차": "래미안장안2차",
    "장안현대홈타운(336)": "장안현대홈타운1차",
}
AREA84 = (78, 86)          # 래미안장안2차 81㎡ 포함
AREA59 = (54, 66)          # 59㎡대 (래미안장안2차는 54·65㎡)
GJ_AREA = (59, 86)
GJ_MAX_DEPOSIT = 80000     # 만원 (광진구 전세 표시 상한)
MONTHS = 24
GJ_MONTHS = 6

KST = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(KST)


def month_list(n):
    y, m, out = now.year, now.month, []
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def call(svc, lawd, ym, page):
    url = (f"{BASE}/{svc}/get{svc}?serviceKey={KEY}&LAWD_CD={lawd}"
           f"&DEAL_YMD={ym}&numOfRows=1000&pageNo={page}")
    last = None
    for attempt in range(8):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                text = r.read().decode("utf-8")
            root = ET.fromstring(text)
            code = root.findtext(".//resultCode")
            if code is not None and code.strip("0") == "":
                total = int(root.findtext(".//totalCount") or 0)
                items = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
                return total, items
            last = root.findtext(".//errMsg") or root.findtext(".//resultMsg") or text[:200]
        except Exception as e:  # 네트워크 오류, 파싱 오류
            last = repr(e)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{svc} {lawd} {ym} p{page}: {last}")


def fetch(svc, lawd, ym):
    total, items = call(svc, lawd, ym, 1)
    page = 2
    while (page - 1) * 1000 < total:
        items += call(svc, lawd, ym, page)[1]
        page += 1
    return items


num = lambda s: float(str(s or 0).replace(",", "")) if str(s or "").strip() else 0
dt = lambda o: f"{o['dealYear']}-{int(o['dealMonth']):02d}-{int(o['dealDay']):02d}"


def main():
    months = month_list(MONTHS)
    tr, rd, rg, tr_all = [], [], [], []
    for i, ym in enumerate(months):
        t = fetch("RTMSDataSvcAptTrade", "11230", ym)
        tr_all += t
        tr += [o for o in t if o.get("umdNm") == "장안동"]
        rd += [o for o in fetch("RTMSDataSvcAptRent", "11230", ym) if o.get("umdNm") == "장안동"]
        if i < GJ_MONTHS:
            rg += [o for o in fetch("RTMSDataSvcAptRent", "11215", ym) if o.get("umdNm") in ("구의동", "광장동")]
        print(ym, len(tr), len(rd), len(rg), flush=True)

    def ptype(o):
        a = num(o.get("excluUseAr"))
        if AREA84[0] <= a <= AREA84[1]:
            return "84"
        if AREA59[0] <= a <= AREA59[1]:
            return "59"
        return None

    deals = sorted(({
        "date": dt(o), "apt": TARGETS[o["aptNm"]], "type": ptype(o), "area": num(o["excluUseAr"]),
        "floor": int(num(o.get("floor"))), "price": int(num(o["dealAmount"])),
        "canceled": "Y" if o.get("cdealType") else "N",
    } for o in tr if o.get("aptNm") in TARGETS and ptype(o)), key=lambda x: x["date"], reverse=True)

    jeonse = sorted(({
        "date": dt(o), "apt": TARGETS[o["aptNm"]], "type": ptype(o), "area": num(o["excluUseAr"]),
        "floor": int(num(o.get("floor"))), "deposit": int(num(o["deposit"])),
        "contract": o.get("contractType") or "-",
    } for o in rd if o.get("aptNm") in TARGETS and ptype(o) and num(o.get("monthlyRent")) == 0),
        key=lambda x: x["date"], reverse=True)

    # 시장 분위기 지표: 장안동·동대문구 월별 거래량, 해제 건수, 직거래 건수
    ind = {}
    for o in tr_all:
        k = dt(o)[:7]
        r = ind.setdefault(k, {"month": k, "gu": 0, "guCanceled": 0, "dong": 0, "dongCanceled": 0, "dongDirect": 0})
        c = bool(o.get("cdealType"))
        r["gu"] += 0 if c else 1
        r["guCanceled"] += 1 if c else 0
        if o.get("umdNm") == "장안동":
            r["dong"] += 0 if c else 1
            r["dongCanceled"] += 1 if c else 0
            if not c and "직거래" in (o.get("dealingGbn") or ""):
                r["dongDirect"] += 1
    indicators = [ind[k] for k in sorted(ind)]

    vc = {}
    for o in tr:
        if not o.get("cdealType"):
            k = dt(o)[:7]
            vc[k] = vc.get(k, 0) + 1
    volume = [{"month": k, "count": vc[k]} for k in sorted(vc)]

    gm = {}
    for o in rg:
        a, dep = num(o.get("excluUseAr")), num(o.get("deposit"))
        if num(o.get("monthlyRent")) != 0 or not (GJ_AREA[0] <= a <= GJ_AREA[1]) or dep > GJ_MAX_DEPOSIT:
            continue
        g = gm.setdefault((o["umdNm"], o["aptNm"]), {"v": [], "a": [], "last": "", "by": int(num(o.get("buildYear")))})
        g["v"].append(dep); g["a"].append(a); g["last"] = max(g["last"], dt(o))
    gwangjin = sorted(({
        "apt": k[1], "dong": k[0], "buildYear": g["by"], "deals": len(g["v"]),
        "medianDeposit": int(statistics.median(g["v"])), "minDeposit": int(min(g["v"])),
        "maxDeposit": int(max(g["v"])), "mainArea": round(statistics.median(g["a"]), 1),
        "lastDate": g["last"],
    } for k, g in gm.items() if len(g["v"]) >= 2), key=lambda x: -x["deals"])

    # 비정상적으로 적으면 기존 파일을 지키고 실패 처리
    if len(deals) < 150 or len(jeonse) < 150 or len(volume) < 18:
        sys.exit(f"건수가 너무 적어 저장하지 않음: deals={len(deals)} jeonse={len(jeonse)} volume={len(volume)}")

    for name, rows in [("deals", deals), ("jeonse", jeonse), ("volume", volume), ("gwangjin", gwangjin), ("indicators", indicators)]:
        with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False)
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"updatedAt": now.isoformat(timespec="minutes"), "source": "국토교통부 실거래가 공개 API"}, f, ensure_ascii=False)
    print("saved", len(deals), len(jeonse), len(volume), len(gwangjin))


if __name__ == "__main__":
    main()
