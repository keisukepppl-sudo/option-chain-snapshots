#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

US_TICKERS = ["SPY", "QQQ", "SOXX", "SMH", "MU", "DRAM"]
US_LEVERAGED_ETFS = {
    "TQQQ": {"underlying":"QQQ", "leverage":3.0},
    "QLD": {"underlying":"QQQ", "leverage":2.0},
    "SQQQ": {"underlying":"QQQ", "leverage":-3.0},
    "SOXL": {"underlying":"SOXX", "leverage":3.0},
    "SOXS": {"underlying":"SOXX", "leverage":-3.0},
}
KOREA_MARKET = {
    "KOSPI": {"yf":"^KS11", "kind":"index"},
    "KOSDAQ": {"yf":"^KQ11", "kind":"index"},
    "Samsung": {"yf":"005930.KS", "kind":"stock"},
    "SK_hynix": {"yf":"000660.KS", "kind":"stock"},
    "KODEX200": {"yf":"069500.KS", "kind":"etf", "underlying":"KOSPI", "leverage":1.0},
    "KODEX_LEVERAGE": {"yf":"122630.KS", "kind":"etf", "underlying":"KOSPI", "leverage":2.0},
    "KODEX_INVERSE": {"yf":"114800.KS", "kind":"etf", "underlying":"KOSPI", "leverage":-1.0},
    "KODEX_200_FUTURES_INVERSE2X": {"yf":"252670.KS", "kind":"etf", "underlying":"KOSPI", "leverage":-2.0},
    "KODEX_SEMICON": {"yf":"091160.KS", "kind":"etf", "underlying":"KoreaSemi", "leverage":1.0},
}
KOREA_COMPONENT_WEIGHTS = {
    "KODEX200": {"Samsung":0.22, "SK_hynix":0.08},
    "KODEX_LEVERAGE": {"Samsung":0.22, "SK_hynix":0.08},
    "KODEX_INVERSE": {"Samsung":0.22, "SK_hynix":0.08},
    "KODEX_200_FUTURES_INVERSE2X": {"Samsung":0.22, "SK_hynix":0.08},
    "KODEX_SEMICON": {"Samsung":0.25, "SK_hynix":0.30},
}

def today_str(): return pd.Timestamp.today().strftime('%Y-%m-%d')
def ensure_dir(p: Path): p.mkdir(parents=True, exist_ok=True)
def fmt_money(x):
    try:
        if pd.isna(x): return 'NA'
        x=float(x)
    except Exception: return str(x)
    s='-' if x<0 else ''; x=abs(x)
    if x>=1e12: return f'{s}${x/1e12:.2f}T'
    if x>=1e9: return f'{s}${x/1e9:.2f}B'
    if x>=1e6: return f'{s}${x/1e6:.2f}M'
    if x>=1e3: return f'{s}${x/1e3:.2f}K'
    return f'{s}${x:.0f}'

def hist(ticker, period='1y'):
    df=yf.Ticker(ticker).history(period=period, auto_adjust=False)
    if df.empty: raise RuntimeError(f'No data for {ticker}')
    return df

def price_return(ticker):
    df=hist(ticker,'10d'); c=df['Close'].dropna(); v=df['Volume'].dropna() if 'Volume' in df else pd.Series(dtype=float)
    spot=float(c.iloc[-1]); prev=float(c.iloc[-2]) if len(c)>=2 else np.nan
    vol=float(v.iloc[-1]) if len(v) else np.nan
    return {'spot':spot,'prev':prev,'ret1d':spot/prev-1 if prev and prev>0 else np.nan,'volume':vol,'dollar_volume':spot*vol if not pd.isna(vol) else np.nan}

def rv(close, window):
    r=np.log(close/close.shift(1)).dropna()
    return float(r.tail(window).std()*math.sqrt(252)) if len(r)>=window else np.nan

def bs_gamma(S,K,T,r,sigma):
    if S<=0 or K<=0 or T<=0 or sigma<=0: return 0.0
    d1=(math.log(S/K)+(r+0.5*sigma*sigma)*T)/(sigma*math.sqrt(T))
    return float(norm.pdf(d1)/(S*sigma*math.sqrt(T)))

def normalize_option_df(df):
    out=df.rename(columns={'impliedVolatility':'iv','openInterest':'oi','lastPrice':'last_price'}).copy()
    for c in ['strike','last_price','bid','ask','volume','oi','iv','T','gamma','delta','public_gex','spot','mid']:
        if c in out: out[c]=pd.to_numeric(out[c], errors='coerce')
    if 'mid' not in out:
        out['mid']=np.where(out.get('ask',0)>0,(out.get('bid',0)+out.get('ask',0))/2,out.get('last_price',np.nan))
    out['type']=out['type'].astype(str).str.lower()
    return out

def load_latest_two(snapshot_dir, ticker):
    folder=Path(snapshot_dir)/ticker.upper(); files=sorted(folder.glob(f'{ticker.upper()}_*.csv')) if folder.exists() else []
    if not files: return None,None,None,None
    latest=normalize_option_df(pd.read_csv(files[-1])); prev=normalize_option_df(pd.read_csv(files[-2])) if len(files)>=2 else None
    return latest,prev,files[-1],files[-2] if len(files)>=2 else None

def infer_side(row):
    oi=row.get('oi_change',np.nan); iv=row.get('iv_change',np.nan); mid=row.get('mid_change',np.nan); vol=row.get('volume',np.nan)
    if pd.isna(oi) or oi<=0: return ('NO_NEW_POSITION_OR_CLOSING',20.0,'OI not increasing')
    buy=sell=0; reasons=[]
    if not pd.isna(iv):
        if iv>0: buy+=2; reasons.append('IV up')
        elif iv<0: sell+=2; reasons.append('IV down')
    if not pd.isna(mid):
        if mid>0: buy+=1; reasons.append('option price up')
        elif mid<0: sell+=1; reasons.append('option price down')
    if not pd.isna(vol) and vol>=abs(oi)*0.5: buy+=0.5; sell+=0.5; reasons.append('volume confirms')
    if buy>sell: return ('LIKELY_CUSTOMER_BUY',min(95,50+(buy-sell)*15),'; '.join(reasons))
    if sell>buy: return ('LIKELY_CUSTOMER_SELL',min(95,50+(sell-buy)*15),'; '.join(reasons))
    return ('AMBIGUOUS',50.0,'; '.join(reasons))

def option_gex_engine(snapshot_dir, outdir, tickers):
    summaries=[]; flow_rows=[]
    for ticker in tickers:
        latest,prev,lf,pf=load_latest_two(snapshot_dir,ticker)
        if latest is None:
            summaries.append({'date':today_str(),'ticker':ticker,'error':'no snapshot'}); continue
        spot=float(latest['spot'].dropna().iloc[-1]) if 'spot' in latest and latest['spot'].notna().any() else np.nan
        if 'public_gex' not in latest or latest['public_gex'].isna().all():
            vals=[]
            for _,r in latest.iterrows():
                g=r.get('gamma',np.nan)
                if pd.isna(g): g=bs_gamma(spot,float(r['strike']),float(r.get('T',1/365)),0.04,float(r.get('iv',0.3)))
                sign=1 if r['type']=='call' else -1
                vals.append(sign*g*float(r.get('oi',0))*100*spot*spot*0.01)
            latest['public_gex']=vals
        net=float(latest['public_gex'].sum())
        grouped=latest.groupby(['strike','type'],as_index=False).agg(oi=('oi','sum'),volume=('volume','sum'),public_gex=('public_gex','sum'))
        pg=grouped.pivot(index='strike',columns='type',values='public_gex').fillna(0)
        po=grouped.pivot(index='strike',columns='type',values='oi').fillna(0)
        call_gex=float(pg['call'].idxmax()) if 'call' in pg and not pg.empty else np.nan
        put_gex=float(pg['put'].idxmin()) if 'put' in pg and not pg.empty else np.nan
        call_oi=float(po['call'].idxmax()) if 'call' in po and not po.empty else np.nan
        put_oi=float(po['put'].idxmax()) if 'put' in po and not po.empty else np.nan
        sg=latest.groupby('strike',as_index=False)['public_gex'].sum().sort_values('strike')
        flip=np.nan
        if not sg.empty:
            signs=np.sign(sg['public_gex'].cumsum()); ch=np.where(np.diff(signs)!=0)[0]
            if len(ch): flip=float(sg.iloc[ch[0]+1]['strike'])
        summaries.append({'date':today_str(),'ticker':ticker,'spot':spot,'snapshot_file':str(lf),'prev_file':str(pf) if pf else '', 'net_gex':net,'gex_regime':'POSITIVE_GEX' if net>0 else 'NEGATIVE_GEX','gamma_flip_approx':flip,'call_gex_wall':call_gex,'put_gex_wall':put_gex,'call_oi_wall':call_oi,'put_oi_wall':put_oi})
        grouped.to_csv(outdir/f'{ticker}_strike_type_gex.csv',index=False)
        if prev is not None:
            key=['contractSymbol'] if 'contractSymbol' in latest and 'contractSymbol' in prev else ['ticker','expiration','strike','type']
            cols=key+['oi','iv','mid','volume','public_gex','gamma','delta','spot']
            m=latest[[c for c in cols if c in latest]].merge(prev[[c for c in cols if c in prev]], on=key, how='left', suffixes=('', '_prev'))
            m['oi_change']=m['oi']-m.get('oi_prev',np.nan); m['iv_change']=m['iv']-m.get('iv_prev',np.nan); m['mid_change']=m['mid']-m.get('mid_prev',np.nan); m['new_public_gex']=m['public_gex']-m.get('public_gex_prev',0)
            cls=m.apply(infer_side,axis=1,result_type='expand'); m['flow_class']=cls[0]; m['confidence']=cls[1]; m['flow_reason']=cls[2]
            dealer_mult=np.where(m['flow_class']=='LIKELY_CUSTOMER_BUY',-1,np.where(m['flow_class']=='LIKELY_CUSTOMER_SELL',1,0))
            m['inferred_dealer_new_gex']=dealer_mult*m['new_public_gex'].fillna(0); m['ticker']=ticker
            top=m.sort_values('oi_change',ascending=False).head(100); top.to_csv(outdir/f'{ticker}_top_oi_change_dealer_flow.csv',index=False); flow_rows.append(top)
    s=pd.DataFrame(summaries); f=pd.concat(flow_rows,ignore_index=True) if flow_rows else pd.DataFrame()
    s.to_csv(outdir/'option_gex_summary.csv',index=False); f.to_csv(outdir/'option_dealer_flow_top.csv',index=False)
    return s,f

def get_aum_yfinance(ticker):
    try:
        info=yf.Ticker(ticker).info or {}
        for k in ['totalAssets','netAssets']:
            v=info.get(k)
            if v and float(v)>0: return float(v),f'yfinance:{k}'
    except Exception: pass
    return np.nan,'missing'

def load_manual_aum(path):
    if not Path(path).exists(): return pd.DataFrame(columns=['date','ticker','aum_manual'])
    df=pd.read_csv(path, comment='#')
    if df.empty: return pd.DataFrame(columns=['date','ticker','aum_manual'])
    df['date']=pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d'); df['ticker']=df['ticker'].astype(str).str.upper(); df['aum_manual']=pd.to_numeric(df['aum'],errors='coerce')
    return df[['date','ticker','aum_manual']]

def cta_engine(tickers):
    rows=[]
    for t in tickers:
        try:
            close=hist(t,'1y')['Close'].dropna(); spot=float(close.iloc[-1]); row={'date':today_str(),'ticker':t,'spot':spot,'ret1d':float(close.iloc[-1]/close.iloc[-2]-1)}; score=0; flow=0; notes=[]
            for w in [20,50,100,200]:
                ma=float(close.rolling(w).mean().iloc[-1]) if len(close)>=w else np.nan; row[f'ma{w}']=ma
                if pd.isna(ma): row[f'dist_ma{w}']=np.nan; continue
                dist=spot/ma-1; row[f'dist_ma{w}']=dist; score+=1 if dist>0 else -1
                if abs(dist)<0.01: notes.append(f'near MA{w}'); flow+=(0.01-abs(dist))*100
                flow+=min(max(dist,-0.05),0.05)*(10 if dist>0 else 20)
            row.update({'cta_score':score,'cta_regime':'CTA_LONG' if score>=3 else ('CTA_SELL_RISK' if score<=-3 else 'CTA_MIXED'),'cta_flow_proxy':flow,'cta_notes':'; '.join(notes),'rv20':rv(close,20),'rv60':rv(close,60)})
            rows.append(row)
        except Exception as e: rows.append({'date':today_str(),'ticker':t,'error':str(e)})
    return pd.DataFrame(rows)

def vol_control_engine(tickers):
    rows=[]
    for t in tickers:
        try:
            close=hist(t,'1y')['Close'].dropna(); r20=rv(close,20); pr20=rv(close.iloc[:-1],20); target=0.10
            exp=min(1.5,target/r20) if r20 and r20>0 else np.nan; pexp=min(1.5,target/pr20) if pr20 and pr20>0 else np.nan; ch=exp-pexp if not pd.isna(exp) and not pd.isna(pexp) else np.nan
            rows.append({'date':today_str(),'ticker':t,'spot':float(close.iloc[-1]),'ret1d':float(close.iloc[-1]/close.iloc[-2]-1),'rv20':r20,'rv60':rv(close,60),'target_vol':target,'vol_control_exposure_proxy':exp,'vol_control_exposure_change':ch,'vol_control_flow_proxy':ch*100 if not pd.isna(ch) else np.nan,'regime':'VOL_CONTROL_BUY' if ch and ch>0 else ('VOL_CONTROL_SELL' if ch and ch<0 else 'NEUTRAL')})
        except Exception as e: rows.append({'date':today_str(),'ticker':t,'error':str(e)})
    return pd.DataFrame(rows)

def us_levered_etf_engine(root, manual_path):
    manual=load_manual_aum(manual_path); hist_file=Path(root)/'us_leveraged_etf_aum_history.csv'; old=pd.read_csv(hist_file) if hist_file.exists() else pd.DataFrame(); rows=[]
    for etf,meta in US_LEVERAGED_ETFS.items():
        try:
            p=price_return(etf); u=price_return(meta['underlying']); aum,src=get_aum_yfinance(etf); man=manual[(manual['date']==today_str())&(manual['ticker']==etf)]
            if not man.empty and not pd.isna(man['aum_manual'].iloc[-1]): aum=float(man['aum_manual'].iloc[-1]); src='manual_csv'
            prev=np.nan
            if not old.empty and 'ticker' in old:
                vals=pd.to_numeric(old[old['ticker']==etf].sort_values('date')['aum'],errors='coerce').dropna(); prev=float(vals.iloc[-1]) if len(vals) else np.nan
            L=meta['leverage']
            if pd.isna(aum): creation=p['dollar_volume']*0.03*np.sign(p['ret1d']-L*u['ret1d']); reb=p['dollar_volume']*0.10*L*(L-1)*u['ret1d']; method='fallback_volume_proxy'
            else: creation=aum-prev*(1+p['ret1d']) if not pd.isna(prev) else np.nan; reb=aum*L*(L-1)*u['ret1d']; method='aum_based'
            rows.append({'date':today_str(),'ticker':etf,'underlying':meta['underlying'],'leverage':L,'etf_price':p['spot'],'etf_ret1d':p['ret1d'],'underlying_ret1d':u['ret1d'],'volume':p['volume'],'dollar_volume':p['dollar_volume'],'aum':aum,'prev_aum':prev,'aum_source':src,'creation_redemption_flow':creation,'rebalance_flow':reb,'total_estimated_flow':(0 if pd.isna(creation) else creation)+(0 if pd.isna(reb) else reb),'method':method})
        except Exception as e: rows.append({'date':today_str(),'ticker':etf,'error':str(e)})
    df=pd.DataFrame(rows); combined=pd.concat([old,df],ignore_index=True).drop_duplicates(['date','ticker'],keep='last') if not old.empty else df.copy(); combined.to_csv(hist_file,index=False); return df

def korea_engine(root, manual_path):
    manual=load_manual_aum(manual_path); hist_file=Path(root)/'korea_etf_aum_history.csv'; old=pd.read_csv(hist_file) if hist_file.exists() else pd.DataFrame(); rows=[]
    try: kospi_ret=price_return(KOREA_MARKET['KOSPI']['yf'])['ret1d']
    except Exception: kospi_ret=np.nan
    for name,meta in KOREA_MARKET.items():
        try:
            p=price_return(meta['yf']); row={'date':today_str(),'name':name,'ticker':meta['yf'],'kind':meta['kind'],'spot':p['spot'],'ret1d':p['ret1d'],'volume':p['volume'],'dollar_volume_local':p['dollar_volume']}
            if meta['kind']=='etf':
                L=meta.get('leverage',1.0); man=manual[(manual['date']==today_str())&(manual['ticker']==name.upper())]
                aum=float(man['aum_manual'].iloc[-1]) if not man.empty and not pd.isna(man['aum_manual'].iloc[-1]) else np.nan; prev=np.nan
                if not old.empty and 'name' in old:
                    vals=pd.to_numeric(old[old['name']==name].sort_values('date')['aum'],errors='coerce').dropna(); prev=float(vals.iloc[-1]) if len(vals) else np.nan
                und=kospi_ret if meta.get('underlying')=='KOSPI' else p['ret1d']
                if pd.isna(aum): creation=p['dollar_volume']*0.03*np.sign(p['ret1d']-L*und); reb=p['dollar_volume']*0.10*L*(L-1)*und; method='fallback_volume_proxy'
                else: creation=aum-prev*(1+p['ret1d']) if not pd.isna(prev) else np.nan; reb=aum*L*(L-1)*und; method='aum_based_manual'
                row.update({'leverage':L,'underlying':meta.get('underlying'),'aum':aum,'prev_aum':prev,'creation_redemption_flow_local':creation,'rebalance_flow_local':reb,'total_estimated_flow_local':(0 if pd.isna(creation) else creation)+(0 if pd.isna(reb) else reb),'method':method})
            rows.append(row)
        except Exception as e: rows.append({'date':today_str(),'name':name,'ticker':meta['yf'],'error':str(e)})
    df=pd.DataFrame(rows); etfs=df[df.get('kind')=='etf'].copy() if 'kind' in df else pd.DataFrame()
    if not etfs.empty:
        comb=pd.concat([old,etfs],ignore_index=True).drop_duplicates(['date','name'],keep='last') if not old.empty else etfs.copy(); comb.to_csv(hist_file,index=False)
    impacts=[]
    for _,r in etfs.iterrows() if not etfs.empty else []:
        total=r.get('total_estimated_flow_local',0)
        for comp,w in KOREA_COMPONENT_WEIGHTS.get(r['name'],{}).items(): impacts.append({'date':today_str(),'source_etf':r['name'],'component':comp,'weight_assumption':w,'estimated_component_flow_local':total*w if not pd.isna(total) else np.nan})
    return df,pd.DataFrame(impacts)

def market_down_rs(tickers):
    try: bench=hist('QQQ','6mo')['Close'].dropna().pct_change(); down=bench[bench<-0.005].index
    except Exception: return pd.DataFrame()
    rows=[]
    for t in tickers:
        try:
            ret=hist(t,'6mo')['Close'].dropna().pct_change(); dd=pd.DataFrame({'stock':ret,'bench':bench}).dropna(); dd=dd.loc[dd.index.intersection(down)]
            if dd.empty: hit=excess=score=np.nan
            else: ex=dd['stock']-dd['bench']; hit=float((ex>0).mean()); excess=float(ex.mean()); score=hit*70+max(min(excess*100,10),-10)*3
            rows.append({'date':today_str(),'ticker':t,'benchmark':'QQQ','down_day_count':len(dd),'down_day_rs_hit_rate':hit,'down_day_avg_excess_return':excess,'down_day_rs_score':score})
        except Exception as e: rows.append({'date':today_str(),'ticker':t,'error':str(e)})
    return pd.DataFrame(rows)

def combined_flow(option_summary,cta,vc,us_etf):
    rows=[]
    for t in US_TICKERS:
        c=cta.loc[cta['ticker']==t,'cta_flow_proxy'].sum() if not cta.empty and 'ticker' in cta else np.nan
        v=vc.loc[vc['ticker']==t,'vol_control_flow_proxy'].sum() if not vc.empty and 'ticker' in vc else np.nan
        g=option_summary.loc[option_summary['ticker']==t,'net_gex'].sum() if not option_summary.empty and 'ticker' in option_summary else np.nan
        e=0.0
        if t=='QQQ' and not us_etf.empty: e=us_etf.loc[us_etf['underlying']=='QQQ','total_estimated_flow'].sum()
        if t in ['SOXX','SMH'] and not us_etf.empty: e=us_etf.loc[us_etf['underlying']=='SOXX','total_estimated_flow'].sum()
        rows.append({'date':today_str(),'ticker':t,'cta_flow_proxy_score':c,'vol_control_flow_proxy_score':v,'levered_etf_flow_usd_est':e,'net_gex_usd_per_1pct':g,'mechanical_flow_proxy_score':(0 if pd.isna(c) else c)+(0 if pd.isna(v) else v)})
    return pd.DataFrame(rows)

def write_report(outdir, dfs):
    report=f'# Phase 2.5 Flow Terminal Report\n\nDate: {today_str()}\n\n'
    for title,df in dfs.items():
        report+=f'## {title}\n\n'
        if df is None or df.empty: report+='_No data._\n\n'; continue
        view=df.copy()
        for col in view.columns:
            if any(k in col.lower() for k in ['flow','gex','aum','dollar']):
                view[col]=view[col].map(lambda x: fmt_money(x) if pd.notna(x) and isinstance(x,(int,float,np.integer,np.floating)) else x)
        report+=view.head(40).to_markdown(index=False)+'\n\n'
    (outdir/'phase25_flow_report.md').write_text(report,encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--outdir',default='daily_flow_outputs'); ap.add_argument('--snapshot-dir',default='option_chain_snapshots'); ap.add_argument('--manual-aum',default='manual_etf_aum.csv'); args=ap.parse_args()
    root=Path(args.outdir); outdir=root/today_str(); ensure_dir(outdir)
    opt_sum,opt_flow=option_gex_engine(Path(args.snapshot_dir),outdir,US_TICKERS)
    cta=cta_engine(US_TICKERS); vc=vol_control_engine(['SPY','QQQ']); us_etf=us_levered_etf_engine(root,Path(args.manual_aum)); korea,kimpact=korea_engine(root,Path(args.manual_aum)); rs=market_down_rs(US_TICKERS); combo=combined_flow(opt_sum,cta,vc,us_etf)
    for name,df in [('cta_signals',cta),('vol_control_proxy',vc),('us_leveraged_etf_flows',us_etf),('korea_market_and_etf',korea),('korea_component_flow_impact',kimpact),('market_down_rs',rs),('combined_mechanical_flow',combo)]: df.to_csv(outdir/f'{name}.csv',index=False)
    write_report(outdir, {'Combined Mechanical Flow':combo,'Option GEX Summary':opt_sum,'Top Option Dealer Flow':opt_flow,'CTA':cta,'Vol Control':vc,'US Leveraged ETF Flow':us_etf,'Korea Market / ETF':korea,'Korea Component Impact':kimpact,'Market Down RS':rs})
    print(f'Saved Phase 2.5 outputs to {outdir}')
if __name__=='__main__': main()
