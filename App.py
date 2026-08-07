"""Modern Streamlit UI for the Pirate Whist league and scorekeeper."""

import base64
import binascii
import hmac
import html
import json
import os
import uuid
import zlib
from pathlib import Path

import streamlit as st

from Competition import (
    add_player, delete_game, load_data, record_game, remove_avatar,
    normalize_avatar_upload, save_avatar, update_player, update_settings,
)
from Game import Game
from LeagueScore import MAX_COMPETITION_PLAYERS, MIN_COMPETITION_PLAYERS
from Simulation import (
    delete_all_simulated_games, delete_simulated_game, generate_simulated_games,
    save_simulated_games, test_mode_enabled,
)
from Statistics import drunkenbolten, hall_of_fame, initials, leaderboard, shots_from_score

st.set_page_config(page_title="Pirate Whist League", page_icon="🃏", layout="wide")
harboe_path = Path(__file__).parent / "assets" / "harboe-original.png"
lygten_path = Path(__file__).parent / "assets" / "lygten-original.png"
harboe_data = base64.b64encode(harboe_path.read_bytes()).decode("ascii")
lygten_data = base64.b64encode(lygten_path.read_bytes()).decode("ascii")
theme_css = """
<style>
  :root { color-scheme:dark; }
  .stApp {
    color:#f3eadc;background-color:#090d11;
    background-image:linear-gradient(105deg,rgba(5,9,13,.82),rgba(8,12,16,.64),rgba(5,8,12,.8)),url("data:image/png;base64,__HARBOE__"),url("data:image/png;base64,__LYGTEN__");
    background-size:cover,clamp(250px,34vw,500px) auto,cover;
    background-position:center,4% 92%,75% center;background-repeat:no-repeat;background-attachment:fixed;
    background-blend-mode:normal,multiply,normal;
  }
  [data-testid="stAppViewContainer"] { background:linear-gradient(100deg,rgba(6,10,14,.52),rgba(8,13,18,.38) 52%,rgba(7,10,14,.52));backdrop-filter:blur(5px); }
  [data-testid="stHeader"] { background:rgba(5,10,16,.78);backdrop-filter:blur(12px); }
  [data-testid="stAppViewContainer"] > .main { background:rgba(6,12,20,.16); }
  .main .block-container { max-width:1160px;padding-top:1.5rem;padding-bottom:4rem; }
  h1,h2,h3 { letter-spacing:-.018em; }
  p,button,input,label { line-height:1.45; }
  .hero { position:relative;overflow:hidden;padding:2.4rem;border:1px solid rgba(205,158,87,.36);border-radius:18px;
          background:linear-gradient(120deg,rgba(18,31,43,.96),rgba(28,21,18,.88));margin-bottom:1rem;
          box-shadow:0 18px 55px rgba(0,0,0,.42),inset 0 1px rgba(255,255,255,.04); }
  .hero:after { content:"";position:absolute;width:150px;height:150px;right:-55px;bottom:-75px;border:2px solid rgba(194,139,71,.12);border-radius:50%;box-shadow:0 0 0 10px rgba(194,139,71,.035); }
  .eyebrow { color:#d3a85f;text-transform:uppercase;letter-spacing:.16em;font-size:.75rem;font-weight:700; }
  .muted { color:#acb5bc;max-width:650px; }
  .playing-card { position:absolute;right:7%;top:18%;padding:.35rem .55rem;background:#e8ddc8;color:#37251d;
                  border-radius:6px;transform:rotate(8deg);font-family:Georgia,serif;font-weight:800;box-shadow:0 8px 20px #0008;opacity:.78; }
  .sticky { display:inline-block;margin-top:.8rem;padding:.42rem .7rem;background:#c7a763;color:#342719;
            font:600 .78rem Georgia,serif;transform:rotate(-1.2deg);box-shadow:2px 4px 10px #0007; }
  .avatar { width:52px;height:52px;border-radius:50%;background:linear-gradient(145deg,#27374a,#15202d);display:flex;
            align-items:center;justify-content:center;font-weight:800;color:#e0bb75;border:2px solid #80623d;box-shadow:0 5px 14px #0007; }
  .podium { padding:1.25rem;border:1px solid rgba(184,138,78,.34);border-radius:13px;text-align:center;
            background:linear-gradient(145deg,rgba(19,32,43,.96),rgba(26,24,22,.94));box-shadow:0 12px 30px #0006; }
  div[data-testid="stMetric"] { background:linear-gradient(145deg,rgba(18,31,43,.96),rgba(22,20,18,.94));
            border:1px solid rgba(179,136,82,.3);padding:14px;border-radius:12px;box-shadow:0 9px 24px #0004; }
  div[data-testid="stMetric"] label, div[data-testid="stMetric"] [data-testid="stMetricValue"] { color:#f1e5d2; }
  div[data-testid="stDataFrame"] { border:1px solid rgba(179,136,82,.3);border-radius:12px;overflow:hidden;box-shadow:0 9px 26px #0005; }
  .stButton > button { border-color:rgba(194,151,91,.42);background:rgba(15,26,36,.88);transition:transform .16s ease,border-color .16s ease; }
  .stButton > button:hover { transform:translateY(-1px);border-color:#c6995d;color:#f6d79c; }
  .stButton > button:focus-visible,button:focus-visible,input:focus-visible { outline:3px solid #e6b968;outline-offset:2px; }
  [data-testid="stExpander"], [data-testid="stForm"] { background:rgba(12,21,29,.9);border-color:rgba(179,136,82,.28); }
  [data-testid="stExpander"] summary { background:#111d26!important;color:#f0e7da!important;border-radius:8px 8px 0 0; }
  [data-testid="stExpander"] summary p,[data-testid="stExpander"] summary span { color:#f0e7da!important; }
  .league-title { margin:.2rem 0 1.25rem;font:800 clamp(2.2rem,7vw,5rem)/.95 Georgia,serif;
                  color:#e3c88f;text-shadow:0 4px 22px #000;letter-spacing:-.035em;transform:rotate(-.3deg);transform-origin:left; }
  .champion { padding:1.4rem 1.6rem;border-radius:18px;background:linear-gradient(120deg,rgba(54,39,20,.96),rgba(16,29,39,.96));
              box-shadow:0 18px 55px #0009,0 0 38px rgba(211,168,95,.12);border:1px solid rgba(229,185,105,.4); }
  .st-key-champion_card { padding:2.1rem 2.3rem 1.8rem;border-radius:15px 20px 14px 18px;background:linear-gradient(116deg,rgba(48,36,22,.96),rgba(15,27,36,.96));
              box-shadow:7px 16px 42px #0009;border:1px solid rgba(213,174,102,.33);margin:0 0 1rem .35rem;transform:rotate(.15deg); }
  .champion-hero { padding:2.2rem 2.4rem;border-radius:15px 20px 14px 18px;background:linear-gradient(116deg,rgba(48,36,22,.96),rgba(15,27,36,.96));
              box-shadow:7px 16px 42px #0009;border:1px solid rgba(213,174,102,.33);margin:0 0 .55rem .35rem;transform:rotate(.15deg); }
  .champion-grid { display:flex;align-items:center;gap:clamp(1.2rem,4vw,3.5rem);margin-top:1rem; }
  .champion-identity { flex:1;min-width:220px;overflow-wrap:anywhere; }
  .champion-name { font:800 clamp(2rem,5vw,3.8rem)/1 Georgia,serif;color:#e8c979;text-shadow:0 0 22px rgba(224,181,91,.18);overflow-wrap:normal;word-break:normal; }
  .champion-real-name { display:block;margin-top:.55rem;color:#c8bdad;font-size:.95rem;font-weight:650;letter-spacing:.04em;overflow-wrap:anywhere; }
  .champion-numbers { display:flex;gap:.7rem; }
  .champion-stat { min-width:105px;padding:.75rem 1rem;background:#0e1720cc;border-radius:8px 12px 9px 10px;box-shadow:3px 7px 16px #0006; }
  .champion-stat small { display:block;color:#a99e8c;margin-bottom:.2rem; }
  .champion-stat strong { font:700 1.7rem Georgia,serif;color:#f2e5cf; }
  .champion-badge { color:#21160b;background:linear-gradient(135deg,#efd38e,#a97833);display:inline-block;
                    padding:.28rem .7rem;border-radius:99px;font-size:.72rem;font-weight:900;letter-spacing:.1em;text-transform:uppercase; }
  .last-place { padding:.8rem 1rem;margin:.8rem 0 1rem;border-radius:10px;background:rgba(27,30,32,.84);
                border-left:3px solid #73787c;color:#d0d2d3;transform:rotate(-.25deg);box-shadow:3px 7px 18px #0005; }
  .last-place small { display:block;color:#969da1;margin-top:.18rem; }
  .last-place-stats { display:flex;gap:1.4rem;margin-top:.7rem;padding-top:.55rem;border-top:1px solid #ffffff12; }
  .last-place-stats strong { display:block;color:#e0e2e3;font:700 1.1rem Georgia,serif; }
  .st-key-positive_scores button { min-height:64px;background:linear-gradient(145deg,#176044,#0d392a);border-color:#3e9a71;font-size:1.35rem;font-weight:800; }
  .st-key-negative_scores button { min-height:64px;background:linear-gradient(145deg,#74342e,#431d1a);border-color:#a95c51;font-size:1.35rem;font-weight:800; }
  .st-key-neutral_score button { min-height:68px;background:linear-gradient(145deg,#555b62,#30353a);border-color:#858b91;font-size:1.45rem;font-weight:900; }
  .st-key-score_back button { min-height:50px;background:rgba(81,64,42,.9);border-color:#b18a55;font-weight:800; }
  .score-player { text-align:center;margin:.2rem 0 1rem; }
  .form { letter-spacing:.08em;font-weight:700; }
  .st-key-main_nav { position:relative;z-index:5;margin:.35rem 0 1rem; }
  .st-key-main_nav [data-testid="stHorizontalBlock"] { display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:.42rem; }
  .st-key-main_nav [data-testid="stColumn"] { width:auto!important;min-width:0!important;flex:none!important; }
  .st-key-main_nav button { min-height:46px;padding:.45rem .35rem;white-space:nowrap; }
  .metric-grid { display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:.65rem;margin:.65rem 0 1.25rem; }
  .metric-tile { min-width:0;padding:.85rem;background:linear-gradient(145deg,rgba(18,31,43,.96),rgba(22,20,18,.94));border:1px solid rgba(179,136,82,.28);border-radius:11px 14px 10px 13px;box-shadow:3px 8px 22px #0004; }
  .metric-tile small { display:block;color:#aeb6bc;font-size:.73rem;margin-bottom:.22rem; }
  .metric-tile strong { display:block;color:#f2e5cf;font:700 1.35rem/1.15 Georgia,serif;overflow-wrap:anywhere; }
  .metric-tile em { display:block;font-size:.72rem;font-style:normal;margin-top:.25rem; }
  .score-change.positive,.metric-tile em.positive { color:#79c99f; }
  .score-change.negative,.metric-tile em.negative { color:#e27870; }
  .score-change.neutral,.metric-tile em.neutral { color:#9da5aa; }
  .profile-head { display:flex;align-items:center;gap:1.2rem;padding:1.15rem 1.3rem;background:rgba(11,20,28,.9);border:1px solid rgba(179,136,82,.28);border-radius:15px 18px 13px 16px;box-shadow:4px 12px 30px #0006;margin-bottom:.6rem; }
  .profile-head>div { min-width:0; }
  .profile-head>.avatar,.profile-head>img,.champion-grid>.avatar,.champion-grid>img,.drunken-card>.avatar,.drunken-card>img,.score-player-head>.avatar,.score-player-head>img { flex-shrink:0; }
  .profile-head h1 { margin:0;font:800 clamp(2rem,5vw,3.5rem)/1 Georgia,serif;overflow-wrap:anywhere; }
  .profile-head p { color:#adb4b9;margin:.45rem 0 0; }
  .rank-card,.history-card,.record-card { background:linear-gradient(145deg,rgba(16,28,38,.96),rgba(24,22,20,.94));border:1px solid rgba(179,136,82,.25);border-radius:11px 15px 10px 13px;box-shadow:3px 9px 24px #0005;padding:1rem;margin:.55rem 0; }
  .player-overview-card { box-sizing:border-box;min-height:178px;padding:1rem;background:linear-gradient(145deg,rgba(16,28,38,.97),rgba(24,22,20,.95));border:1px solid rgba(179,136,82,.28);border-radius:12px 16px 11px 14px;box-shadow:3px 9px 24px #0005;transition:transform .16s ease,border-color .16s ease; }
  .player-overview-head { display:flex;align-items:center;gap:.75rem;min-width:0; }.player-overview-name{font:700 1.12rem/1.18 Georgia,serif;min-width:0;overflow-wrap:anywhere}.player-overview-rank{margin-left:auto;color:#d7ae69;font-weight:800;white-space:nowrap}
  .player-overview-stats { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.45rem;margin-top:.9rem;padding-top:.7rem;border-top:1px solid #ffffff12; }.player-overview-stats small{display:block;color:#9fa8ae;font-size:.7rem}.player-overview-stats strong{color:#f1e6d3;font:700 1.05rem Georgia,serif}
  [class*="st-key-player_card_"] { position:relative; }.st-key-player_grid [data-testid="stHorizontalBlock"]{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-items:stretch;gap:.7rem}.st-key-player_grid [data-testid="stColumn"]{display:flex;flex-direction:column;width:auto!important;min-width:0!important;flex:none!important}.st-key-player_grid [class*="st-key-player_card_"]{height:100%;margin-bottom:1rem}
  [class*="st-key-player_card_"] > .stElementContainer:has(.stButton) { position:absolute;inset:0 0 -1rem;z-index:3;height:auto; }
  [class*="st-key-player_card_"] .stButton { position:static;margin:0;height:100%; }
  [class*="st-key-player_card_"] .stButton button { position:static!important;width:100%!important;height:100%!important;min-height:100%!important;opacity:0;cursor:pointer;border-radius:12px; }
  [class*="st-key-player_card_"]:hover .player-overview-card,[class*="st-key-player_card_"]:hover .rank-card,[class*="st-key-player_card_"]:hover .champion-hero { transform:translateY(-1px);border-color:rgba(214,170,104,.58); }
  [class*="st-key-player_card_"]:has(button:focus-visible) .player-overview-card,[class*="st-key-player_card_"]:has(button:focus-visible) .rank-card,[class*="st-key-player_card_"]:has(button:focus-visible) .champion-hero { outline:3px solid #e6b968;outline-offset:2px; }
  .drunken-card { display:flex;align-items:center;gap:1rem;padding:1.1rem 1.2rem;background:linear-gradient(145deg,rgba(36,30,24,.96),rgba(13,25,34,.96));border:1px solid rgba(188,139,79,.38);border-radius:13px 17px 12px 15px;box-shadow:4px 11px 28px #0006; }
  .drunken-card>div { min-width:0;overflow-wrap:anywhere; }.drunken-card strong { color:#f0dfc1;font:800 1.35rem Georgia,serif;overflow-wrap:anywhere; }.drunken-card p{color:#b9c0c4;margin:.35rem 0 0;font-size:.82rem;overflow-wrap:anywhere}.drunken-title{color:#d6a95e;font-size:.73rem;font-weight:900;letter-spacing:.08em;text-transform:uppercase;margin-bottom:.2rem}
  .recent-game-card { padding:1rem 1.1rem;background:linear-gradient(145deg,rgba(15,28,38,.97),rgba(24,22,20,.95));border:1px solid rgba(179,136,82,.28);border-radius:12px 16px 11px 14px;box-shadow:3px 9px 24px #0005;margin-top:.7rem; }
  .recent-game-head { display:flex;align-items:center;justify-content:space-between;gap:.6rem;color:#b8c0c5;font-size:.78rem; }.game-status{padding:.2rem .5rem;border-radius:99px;font-weight:800}.game-status.eligible{color:#9ed7b7;background:#183c2d}.game-status.excluded{color:#c7c9ca;background:#35393c}
  .recent-game-winner { margin:.65rem 0 .12rem;color:#ead09a;font:800 1.22rem Georgia,serif;overflow-wrap:anywhere; }.recent-game-card>small{color:#9fa8ad}.recent-game-podium{display:grid;gap:.3rem;margin-top:.75rem;padding-top:.65rem;border-top:1px solid #ffffff12}.recent-game-podium span{display:grid;grid-template-columns:2rem minmax(0,1fr) auto;align-items:center;gap:.25rem;color:#d7d9da;overflow-wrap:anywhere}.recent-game-podium b{color:#cba05c}.recent-game-podium strong{color:#f0dfc8}
  [class*="st-key-game_card_"] button { min-height:44px;margin-top:.15rem; }
  .rank-head { display:flex;align-items:center;gap:.8rem; }
  .rank-number { color:#d7ae69;font:800 1.45rem Georgia,serif;min-width:2rem;text-align:center; }
  .rank-name { flex:1;font:700 1.2rem Georgia,serif;min-width:0;overflow-wrap:anywhere; }
  .league-identity { display:block;line-height:1.15; }
  .league-identity .identity-title { display:block;font-weight:800; }
  .league-identity small { display:block;margin-top:.25rem;color:#9fa7ac;font:600 .72rem/1.2 system-ui,sans-serif;letter-spacing:.025em; }
  .league-identity.champion .identity-title { color:#e6c574;text-shadow:0 0 14px rgba(224,181,91,.16); }
  .league-identity.last .identity-title { color:#b8bdc0; }
  .profile-title { display:inline-block;margin-top:.45rem;padding:.24rem .6rem;border-radius:99px;font-size:.72rem;font-weight:800; }
  .profile-title.champion { color:#241a0b;background:linear-gradient(135deg,#ecd28d,#aa7937); }
  .profile-title.last { color:#d5d7d8;background:#34383b;border:1px solid #656b6f; }
  .rank-score { text-align:right; }.rank-score strong { display:block;font:700 1.35rem Georgia,serif; }.rank-score small { display:block; }
  .rank-average { display:flex;align-items:end;justify-content:space-between;margin-top:.75rem;padding:.65rem .75rem;background:#ffffff08;border-left:3px solid #c69a58;border-radius:7px; }.rank-average small{color:#c4b69f;font-weight:750}.rank-average strong{color:#f0dfc2;font:800 1.35rem Georgia,serif}
  .rank-stats { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.4rem;margin-top:.55rem; }
  .rank-stats span { color:#b2bac0;font-size:.75rem; }.rank-stats strong { display:block;color:#f1e6d3;font-size:.95rem; }
  .form-badges { display:flex;gap:.28rem;flex-wrap:wrap;margin-top:.7rem; }
  .place { display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:#38434b;color:#eef0ee;font-size:.75rem;font-weight:800; }
  .place.p1 { background:#8b6a2c;color:#fff0bd; }.place.p2 { background:#456f65;color:#e6fff7; }.place.last { background:#713b36;color:#ffe3df; }
  .history-card { display:grid;grid-template-columns:1.25fr .55fr .75fr 1.35fr;gap:.55rem;align-items:center; }
  .history-card small,.record-card small { color:#aeb6bc; }
  .record-card { min-height:145px; }.record-card h3 { margin:.05rem 0 .7rem;font-size:1rem;color:#cdbb9d; }.record-card strong { display:block;font:800 1.45rem Georgia,serif; }.record-card span { color:#d5aa63;font-weight:800; }
  .signature-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.7rem;margin:.55rem 0 1.15rem; }
  .signature-card { padding:1rem 1.05rem;background:linear-gradient(145deg,rgba(30,31,27,.96),rgba(14,26,35,.95));border:1px solid rgba(203,158,87,.34);border-radius:12px 16px 11px 14px;box-shadow:3px 9px 24px #0005; }
  .signature-card small { display:block;color:#b4aaa0;margin-bottom:.25rem; }.signature-card strong { color:#e7c67d;font:800 1.7rem Georgia,serif; }.signature-card p { color:#b8c0c5;font-size:.78rem;margin:.4rem 0 0; }
  [class*="st-key-record_summary_"] button { justify-content:flex-start;text-align:left;white-space:normal;height:auto;min-height:58px;padding:.7rem .85rem;line-height:1.3;background:rgba(14,25,34,.94);overflow-wrap:anywhere; }
  .record-card h3,.record-card strong { overflow-wrap:anywhere; }
  .score-player-head { display:flex;align-items:center;justify-content:center;gap:1rem;margin:.5rem 0 1rem; }.score-player-head>div{min-width:0}.score-player-name{margin:.1rem 0 0;font-size:2.75rem;font-weight:800;line-height:1.1;overflow-wrap:anywhere;}.score-player-head .eyebrow{text-align:left;}
  .standing-row { display:flex;justify-content:space-between;align-items:center;gap:.5rem;padding:.55rem .7rem;margin:.3rem 0;background:#ffffff08;border-radius:8px; }.standing-row strong{min-width:0;overflow-wrap:anywhere}.standing-row>span{flex-shrink:0}.standing-row:first-child{border-left:3px solid #d0a75e;}
  .st-key-positive_scores [data-testid="stHorizontalBlock"],.st-key-negative_scores [data-testid="stHorizontalBlock"] { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.55rem; }
  .st-key-positive_scores [data-testid="stColumn"],.st-key-negative_scores [data-testid="stColumn"] { width:auto!important;min-width:0!important;flex:none!important; }
  .st-key-neutral_score button { width:100%; }
  [data-testid="stAlert"] { background:rgba(16,31,42,.94);border:1px solid rgba(113,157,181,.34);color:#e8edf0; }
  [data-testid="stAlert"] p,[data-testid="stAlert"] div { color:#e8edf0!important; }
  [data-testid="stRadio"] label p,[data-testid="stCheckbox"] label p,[data-testid="stWidgetLabel"] p { color:#e8e0d4!important; }
  [data-testid="stCaptionContainer"] { color:#b9c0c5; }
  iframe[data-testid="stIFrame"][srcdoc*="stMain"] { visibility:hidden;pointer-events:none; }
  @media(max-width:950px){
    .champion-grid{flex-wrap:wrap}.champion-numbers{width:100%;display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}.champion-stat{min-width:0}
    .metric-grid{grid-template-columns:repeat(3,minmax(0,1fr))}
  }
  @media(pointer:coarse){
    .stApp{background-attachment:scroll}.stButton>button,.stFormSubmitButton>button,[data-testid="stTabs"] [role="tab"]{min-height:48px}
  }
  @media(max-width:700px){
    .stApp{background-size:cover,230px auto,auto 100%;background-position:center,-35px 80%,62% center;background-attachment:scroll;}h1:has(>[data-testid="stHeaderActionElements"]){font-size:clamp(1.6rem,8vw,2.15rem)!important;line-height:1.1!important;overflow-wrap:normal!important;word-break:normal!important}
    .main .block-container{padding:1rem .85rem 3.25rem}.hero{padding:1.35rem}.podium{padding:.8rem}.playing-card{right:4%;top:12%;opacity:.38}.sticky{font-size:.7rem}
    .stButton>button,.stFormSubmitButton>button,[data-testid="stTabs"] [role="tab"]{min-height:48px}.st-key-main_nav [data-testid="stHorizontalBlock"]{grid-template-columns:repeat(3,minmax(0,1fr));}.st-key-main_nav button{font-size:.78rem;min-height:44px}
    .st-key-positive_scores button,.st-key-negative_scores button{min-height:68px;font-size:1.45rem}.champion{padding:1rem}
    .champion-hero{padding:1.15rem;margin-left:0}.champion-grid{align-items:flex-start;flex-wrap:wrap;gap:1rem}.champion-grid>.avatar,.champion-grid>img{width:96px!important;height:96px!important}.champion-identity{min-width:48%}.champion-name{font-size:2.1rem;overflow-wrap:normal;word-break:normal}
    .score-player-name{font-size:clamp(1.55rem,8vw,2rem);overflow-wrap:anywhere;word-break:break-word}
    .champion-numbers{width:100%;display:grid;grid-template-columns:repeat(3,1fr);gap:.4rem}.champion-stat{min-width:0;padding:.55rem}.champion-stat small{font-size:.66rem}.champion-stat strong{font-size:1.25rem}
    .league-title{font-size:2.55rem;margin-bottom:.8rem}.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:.45rem}.metric-tile{padding:.7rem}.metric-tile strong{font-size:1.15rem}
    .profile-head{align-items:center;padding:1rem;gap:.8rem}.profile-head>.avatar,.profile-head>img{width:72px!important;height:72px!important}.profile-head h1{font-size:2rem}.profile-head p{font-size:.75rem}
    .rank-stats{grid-template-columns:repeat(3,minmax(0,1fr))}.history-card{grid-template-columns:1fr 1fr}.signature-grid{grid-template-columns:1fr}.player-overview-card{min-height:154px;padding:.85rem}.player-overview-name{font-size:1rem}.st-key-player_grid [data-testid="stHorizontalBlock"]{grid-template-columns:1fr;gap:.55rem}.recent-game-podium span{grid-template-columns:1.7rem 1fr auto}.drunken-card{padding:.9rem}
    [class*="st-key-player_card_detail_"] .rank-head{display:grid;grid-template-columns:2rem 44px minmax(0,1fr);gap:.45rem .6rem}
    [class*="st-key-player_card_detail_"] .rank-score{grid-column:2/4;text-align:left;display:flex;align-items:baseline;gap:.45rem;min-width:0}
    [class*="st-key-player_card_detail_"] .rank-score strong{font-size:1.2rem;flex-shrink:0}
    [class*="st-key-player_card_detail_"] .rank-score small{min-width:0;overflow-wrap:anywhere}
    [data-testid="stTabs"] [data-baseweb="tab-list"]{overflow-x:auto;scrollbar-width:none}[data-testid="stTabs"] [role="tab"]{white-space:nowrap;padding-left:.75rem;padding-right:.75rem}
    [data-testid="stRadio"] [role="radiogroup"]{display:flex;flex-wrap:wrap;gap:.15rem .65rem}
    .st-key-setup_player_0 [data-testid="stHorizontalBlock"],.st-key-setup_player_1 [data-testid="stHorizontalBlock"],.st-key-setup_player_2 [data-testid="stHorizontalBlock"],.st-key-setup_player_3 [data-testid="stHorizontalBlock"],.st-key-setup_player_4 [data-testid="stHorizontalBlock"],.st-key-setup_player_5 [data-testid="stHorizontalBlock"],.st-key-setup_player_6 [data-testid="stHorizontalBlock"]{display:grid;grid-template-columns:1fr 88px;gap:.5rem}.st-key-setup_player_0 [data-testid="stColumn"],.st-key-setup_player_1 [data-testid="stColumn"],.st-key-setup_player_2 [data-testid="stColumn"],.st-key-setup_player_3 [data-testid="stColumn"],.st-key-setup_player_4 [data-testid="stColumn"],.st-key-setup_player_5 [data-testid="stColumn"],.st-key-setup_player_6 [data-testid="stColumn"]{width:auto!important;min-width:0!important;flex:none!important}
  }
  @media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;transition:none!important;animation:none!important;}}
</style>
""".replace("__HARBOE__", harboe_data).replace("__LYGTEN__", lygten_data)
st.markdown(theme_css, unsafe_allow_html=True)

DEFAULT_STATE = {
    "phase": "home", "game": None, "game_type": None, "current_player_idx": 0,
    "player_names": ["", "", ""], "competition_saved": False,
    "competition_created_in_session": False,
    "selected_player_id": None, "selected_game_id": None, "competition_ids": {},
    "active_game_id": None,
    "score_history": [],
    "expanded_record_ids": [],
    "simulation_preview": [],
    "scroll_to_top": False,
}
for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value

DRAFT_VERSION = 1
MAX_DRAFT_TOKEN_CHARS = 20_000
MAX_DRAFT_BYTES = 65_536


def _encode_game_draft(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_DRAFT_BYTES:
        raise ValueError("Det igangværende spil er for stort til at gemme sikkert")
    return base64.urlsafe_b64encode(zlib.compress(raw, level=9)).decode("ascii").rstrip("=")


def _decode_game_draft(token: str) -> dict:
    if not isinstance(token, str) or not token or len(token) > MAX_DRAFT_TOKEN_CHARS:
        raise ValueError("Ugyldig game draft")
    compressed = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(compressed, MAX_DRAFT_BYTES + 1)
    if len(raw) > MAX_DRAFT_BYTES or decompressor.unconsumed_tail:
        raise ValueError("Game draft er for stor")
    raw += decompressor.flush()
    if len(raw) > MAX_DRAFT_BYTES:
        raise ValueError("Game draft er for stor")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Ugyldig game draft")
    return payload


def save_active_game_draft() -> None:
    game = st.session_state.game
    if game is None:
        return
    game_type = st.session_state.game_type
    stable_ids = (
        [st.session_state.competition_ids[player.id] for player in game.players]
        if game_type == "competition" else []
    )
    payload = {
        "version": DRAFT_VERSION,
        "game_type": game_type,
        "active_game_id": st.session_state.active_game_id,
        "location": st.session_state.get("location"),
        "competition_ids": stable_ids,
        "game": game.snapshot(),
    }
    st.query_params["draft"] = _encode_game_draft(payload)


def clear_active_game_draft() -> None:
    if "draft" in st.query_params:
        del st.query_params["draft"]


def restore_active_game_draft() -> None:
    token = st.query_params.get("draft")
    if not token or st.session_state.game is not None:
        return
    try:
        payload = _decode_game_draft(token)
        if payload.get("version") != DRAFT_VERSION or payload.get("game_type") not in ("temporary", "competition"):
            raise ValueError("Ukendt game draft-version")
        active_game_id = payload.get("active_game_id")
        location = payload.get("location")
        if not isinstance(active_game_id, str) or not active_game_id or len(active_game_id) > 128:
            raise ValueError("Ugyldigt spil-ID")
        if location is not None and (not isinstance(location, str) or len(location) > 200):
            raise ValueError("Ugyldig lokation")
        snapshot = payload.get("game")
        if not isinstance(snapshot, dict):
            raise ValueError("Ugyldig game draft")

        competition_ids = {}
        if payload["game_type"] == "competition":
            stable_ids = payload.get("competition_ids")
            names = snapshot.get("players")
            if not isinstance(stable_ids, list) or not isinstance(names, list) or len(stable_ids) != len(names):
                raise ValueError("Ugyldige konkurrencespillere")
            if any(not isinstance(player_id, str) for player_id in stable_ids) or len(set(stable_ids)) != len(stable_ids):
                raise ValueError("Ugyldige konkurrencespillere")
            players = {player["id"]: player for player in load_data()["players"]}
            if any(player_id not in players for player_id in stable_ids):
                raise ValueError("En spiller i draften findes ikke længere")
            snapshot["players"] = [players[player_id]["name"] for player_id in stable_ids]
            competition_ids = {index: player_id for index, player_id in enumerate(stable_ids, 1)}

        game, score_history, player_index = Game.from_snapshot(snapshot)
        st.session_state.game = game
        st.session_state.game_type = payload["game_type"]
        st.session_state.competition_ids = competition_ids
        st.session_state.current_player_idx = player_index
        st.session_state.competition_saved = False
        st.session_state.competition_created_in_session = False
        st.session_state.active_game_id = active_game_id
        st.session_state.location = location
        st.session_state.score_history = score_history
        st.session_state.phase = "finished" if game.is_finished else "playing"
        st.session_state.scroll_to_top = True
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError, zlib.error, binascii.Error):
        clear_active_game_draft()
        st.warning("Det gemte igangværende spil var ugyldigt og blev derfor ikke gendannet.")


def authentication_gate() -> None:
    """Optional shared league gate; production deployments should configure it."""
    expected = os.environ.get("PIRATE_WHIST_LEAGUE_PASSWORD")
    if not expected or st.session_state.get("league_authenticated"):
        return
    st.markdown('<div class="eyebrow">Pirat Whist 6700</div><div class="league-title">Liga-login</div>', unsafe_allow_html=True)
    password = st.text_input("Liga-password", type="password", autocomplete="current-password")
    if st.button("Log ind", type="primary", width="stretch"):
        if hmac.compare_digest(password, expected):
            st.session_state.league_authenticated = True
            st.rerun()
        st.error("Forkert password")
    st.stop()


def admin_gate() -> None:
    """Require a separate admin role when the league is password protected."""
    league_password = os.environ.get("PIRATE_WHIST_LEAGUE_PASSWORD")
    expected = os.environ.get("PIRATE_WHIST_ADMIN_PASSWORD")
    if not expected and not league_password:  # Explicit local-development mode.
        return
    if not expected:
        st.error("Admin-adgang er deaktiveret, indtil PIRATE_WHIST_ADMIN_PASSWORD er konfigureret.")
        st.stop()
    if st.session_state.get("admin_authenticated"):
        return
    st.subheader("Admin-login")
    password = st.text_input("Admin-password", type="password", key="admin_password", autocomplete="current-password")
    if st.button("Lås admin op", type="primary", width="stretch"):
        if hmac.compare_digest(password, expected):
            st.session_state.admin_authenticated = True
            st.rerun()
        st.error("Forkert admin-password")
    st.stop()


def admin_access_granted() -> bool:
    """Return whether destructive development controls may be rendered."""
    expected = os.environ.get("PIRATE_WHIST_ADMIN_PASSWORD")
    if expected:
        return bool(st.session_state.get("admin_authenticated"))
    return not bool(os.environ.get("PIRATE_WHIST_LEAGUE_PASSWORD"))


def navigate(phase: str) -> None:
    st.session_state.phase = phase
    st.session_state.scroll_to_top = True
    st.rerun()


def navigation() -> None:
    with st.container(key="main_nav"):
        cols = st.columns(6)
        items = [
            ("Forside", "home"), ("Leaderboard", "leaderboard"), ("Historik", "recent_games"),
            ("Rekorder", "hall_of_fame"), ("Spillere", "players"), ("Admin", "admin"),
        ]
        for col, (label, page) in zip(cols, items):
            if col.button(label, key=f"nav_{st.session_state.phase}_{page}", width="stretch",
                          type="primary" if st.session_state.phase == page else "secondary"):
                navigate(page)


def avatar_markup(player: dict, size: int = 52) -> str:
    if player.get("avatar"):
        path = Path(__file__).parent / player["avatar"]
        if path.exists():
            mime = "image/png" if path.suffix.lower() == ".png" else "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return f'<img src="data:{mime};base64,{encoded}" alt="" style="width:{size}px;height:{size}px;border-radius:50%;object-fit:cover;border:2px solid #80623d">'
    return f'<div class="avatar" style="width:{size}px;height:{size}px">{html.escape(initials(player["name"]))}</div>'


def identity_markup(player: dict) -> str:
    """Render a current league title with the stable player name underneath."""
    title = player.get("league_title")
    if not title:
        return html.escape(player["name"])
    kind = player["league_title_kind"]
    icon = "👑" if kind == "champion" else "🗑️"
    return (
        f'<span class="league-identity {kind}"><span class="identity-title">'
        f'{icon} {html.escape(title)}</span><small>{html.escape(player["name"])}</small></span>'
    )


def identity_text(player: dict) -> str:
    title = player.get("league_title")
    if not title:
        return player["name"]
    icon = "👑" if player["league_title_kind"] == "champion" else "🗑️"
    return f'{icon} {title} · {player["name"]}'


def title_badge_markup(player: dict) -> str:
    if not player.get("league_title"):
        return ""
    kind = player["league_title_kind"]
    icon = "👑" if kind == "champion" else "🗑️"
    return f'<span class="profile-title {kind}">{icon} {html.escape(player["league_title"])}</span>'


def clickable_player_card(player: dict, key: str, rank_label: str | None = None) -> None:
    rank = rank_label or (f'#{player["rank"]}' if player.get("rank") else "Unranked")
    with st.container(key=f"player_card_{key}"):
        st.markdown(f'''<div class="player-overview-card"><div class="player-overview-head">{avatar_markup(player, 58)}
        <div class="player-overview-name">{identity_markup(player)}</div><span class="player-overview-rank">{html.escape(rank)}</span></div>
        <div class="player-overview-stats"><span><small>Liga-score</small><strong>{player["league_score"]:.1f}</strong></span>
        <span><small>Ligaspil</small><strong>{player["eligible_games"]}</strong></span></div></div>''', unsafe_allow_html=True)
        if st.button(f'Åbn profil for {player["name"]}', key=f"open_{key}", width="stretch"):
            open_player(player["id"])


def open_player(player_id: str) -> None:
    st.session_state.selected_player_id = player_id
    navigate("player_profile")


def open_game(game_id: str) -> None:
    st.session_state.selected_game_id = game_id
    navigate("game_detail")


def form_badges(values: list[int], participant_count: int | None = None) -> str:
    if not values:
        return '<span class="muted">Ingen form endnu</span>'
    badges = []
    for value in values:
        css = "p1" if value == 1 else "p2" if value == 2 else "last" if participant_count and value == participant_count else ""
        badges.append(f'<span class="place {css}" aria-label="Placering {value}">{value}</span>')
    return "".join(badges)


def score_change_tone(value: float) -> str:
    displayed = round(value, 1)
    if displayed > 0:
        return "positive"
    if displayed < 0:
        return "negative"
    return "neutral"


def format_score_change(value: float) -> str:
    displayed = round(value, 1)
    return "0.0" if displayed == 0 else f"{displayed:+.1f}"


def metric_grid(items: list[tuple[str, object, str | None]], delta_tone: str = "neutral") -> None:
    tiles = []
    for label, value, delta in items:
        delta_html = f'<em class="{delta_tone}">{html.escape(str(delta))}</em>' if delta else ""
        tiles.append(f'<div class="metric-tile"><small>{html.escape(label)}</small><strong>{html.escape(str(value))}</strong>{delta_html}</div>')
    st.markdown(f'<div class="metric-grid">{"".join(tiles)}</div>', unsafe_allow_html=True)


def render_drunkenbolten(data: dict) -> None:
    record = drunkenbolten(data)
    st.subheader("Drukkenbolten")
    if not record["holders"]:
        st.info("Drukkenbolten uddeles efter det første spil med registrerede shots.")
        return
    if len(record["holders"]) > 1:
        st.caption("Delt rekord")
    bottles = record["vodka_bottles"]
    bottle_text = str(int(bottles)) if bottles.is_integer() else f"{bottles:.1f}".replace(".", ",")
    bottle_unit = "flaske" if bottles == 1 else "flasker"
    for holder in record["holders"]:
        with st.container(key=f"player_card_drunkenbolten_{holder['id']}"):
            st.markdown(f'''<div class="drunken-card">{avatar_markup(holder, 72)}<div>
            <div class="drunken-title">🍾 Drukkenbolten</div><strong>{html.escape(holder["name"])}</strong>
            <p>{record["shots"]} shots modtaget · cirka {record["estimated_cost_dkk"]} kr.<br>
            Svarer til {bottle_text} {bottle_unit} vodka</p></div></div>''', unsafe_allow_html=True)
            if st.button(f'Åbn profil for {holder["name"]}', key=f"open_drunkenbolten_{holder['id']}", width="stretch"):
                open_player(holder["id"])


def home_screen() -> None:
    data = load_data()
    board = leaderboard(data)
    official = board["official"]
    leader = official[0] if official else None
    last = official[-1] if len(official) > 1 else None
    st.markdown('<div class="eyebrow">Pirat Whist 6700</div><div class="league-title">Den Polerede<br>Tips Liga</div>', unsafe_allow_html=True)
    if leader:
        with st.container(key="player_card_home_champion"):
            champion_html = f'''<div class="champion-hero"><span class="champion-badge">👑 Officiel ligamester</span>
            <div class="champion-grid">{avatar_markup(leader, 150)}<div class="champion-identity"><div class="champion-name">{html.escape(leader["league_title"])}</div>
            <small class="champion-real-name">{html.escape(leader["name"])}</small></div>
            <div class="champion-numbers"><div class="champion-stat"><small>Rangering</small><strong>#1</strong></div>
            <div class="champion-stat"><small>Liga-score</small><strong>{leader["league_score"]:.1f}</strong></div>
            <div class="champion-stat"><small>Winstreak</small><strong>{leader["current_streak"]}</strong></div></div></div></div>'''
            st.markdown(champion_html, unsafe_allow_html=True)
            if st.button(f'Åbn profil for {leader["name"]}', key="open_home_champion", width="stretch"):
                open_player(leader["id"])
    if last:
        st.markdown(f'''<div class="last-place">{identity_markup(last)}<div class="last-place-stats">
        <span><small>Gennemsnitsplacering</small><strong>{last["average_placement"]:.2f}</strong></span>
        <span><small>Tabte spil</small><strong>{last["last_places"]}</strong></span></div></div>''', unsafe_allow_html=True)
    navigation()
    left, right = st.columns(2)
    if left.button("Start midlertidigt spil", type="primary", width="stretch"):
        st.session_state.game_type = "temporary"; navigate("temporary_setup")
    if right.button("Start konkurrencespil", width="stretch"):
        st.session_state.game_type = "competition"; navigate("competition_setup")
    st.subheader("Toppen lige nu")
    top = board["official"][:3] or board["provisional"][:3]
    showing_unranked = not board["official"]
    if not top:
        st.info("Ingen spillere endnu.")
    else:
        with st.container(key="player_grid"):
            for row_start in range(0, len(top), 2):
                columns = st.columns(2)
                for index, (column, row) in enumerate(zip(columns, top[row_start:row_start + 2]), row_start + 1):
                    with column:
                        clickable_player_card(row, f"home_{row['id']}", "Unranked" if showing_unranked else f"#{index}")
    render_drunkenbolten(data)
    render_recent_games(data, limit=3)


def players_screen() -> None:
    navigation()
    st.title("Spillerprofiler")
    st.caption("Tryk på en spiller for at åbne profil, statistik og spilhistorik.")
    board = leaderboard(load_data())
    players = board["official"] + board["provisional"]
    if not players:
        st.info("Ingen spillere endnu.")
        return
    with st.container(key="player_grid"):
        for row_start in range(0, len(players), 2):
            columns = st.columns(2)
            for column, player in zip(columns, players[row_start:row_start + 2]):
                with column:
                    clickable_player_card(player, f"overview_{player['id']}")


def leaderboard_screen() -> None:
    navigation(); st.title("Leaderboard")
    st.caption("Den officielle rækkefølge er gennemsnittet af præstationsscore i kvalificerede spil med 5–7 spillere.")
    board = leaderboard(load_data())
    if board["official"]:
        st.subheader("Podiet")
        cols = st.columns(min(3, len(board["official"])))
        for col, row in zip(cols, board["official"][:3]):
            with col:
                clickable_player_card(row, f"podium_{row['id']}", f"#{row['rank']}")
        render_leaderboard_rows(board["official"])
    else:
        st.info("Ingen officielle spillere endnu. Der kræves fem gennemførte spil.")
    st.subheader("Unranked")
    if board["provisional"]: render_leaderboard_rows(board["provisional"], provisional=True)
    else: st.caption("Ingen unranked spillere.")


def render_leaderboard_rows(rows: list[dict], provisional: bool = False) -> None:
    for index, row in enumerate(rows, 1):
        rank = "P" if provisional else f"#{row.get('rank', index)}"
        latest_tone = score_change_tone(row["latest_change"])
        latest_text = format_score_change(row["latest_change"])
        card = f'''<div class="rank-card"><div class="rank-head"><div class="rank-number">{rank}</div>
        {avatar_markup(row, 48)}<div class="rank-name">{identity_markup(row)}</div>
        <div class="rank-score"><strong>{row["league_score"]:.1f}</strong><small class="score-change {latest_tone}">{latest_text} senest</small></div></div>
        <div class="rank-average"><small>Gennemsnitsplacering</small><strong>{row["average_placement"]:.2f}</strong></div>
        <div class="rank-stats"><span>Ligaspil<strong>{row["eligible_games"]}</strong></span><span>Sejre<strong>{row["wins"]}</strong></span>
        <span>Win rate<strong>{row["win_rate"]:.0f}%</strong></span></div>
        <div class="form-badges">{form_badges(row["recent_form"])}</div></div>'''
        with st.container(key=f"player_card_leaderboard_{row['id']}"):
            st.markdown(card, unsafe_allow_html=True)
            if st.button(f'Åbn profil for {row["name"]}', key=f"open_leaderboard_{row['id']}", width="stretch"):
                open_player(row["id"])


def player_profile_screen() -> None:
    navigation(); data = load_data(); player_id = st.session_state.selected_player_id
    if not player_id or not any(p["id"] == player_id for p in data["players"]):
        st.error("Spilleren findes ikke."); return
    board_data = leaderboard(data)
    all_rows = board_data["official"] + board_data["provisional"]
    stats = next(row for row in all_rows if row["id"] == player_id)
    rank = next((row["rank"] for row in board_data["official"] if row["id"] == player_id), None)
    status = "Unranked" if stats["provisional"] else f"Rangering #{rank}"
    st.markdown(f'''<div class="profile-head">{avatar_markup(stats, 96)}<div><h1>{html.escape(stats["name"])}</h1>
    {title_badge_markup(stats)}<p>{status} · Medlem siden {stats["joined_at"][:10]}</p></div></div>''', unsafe_allow_html=True)
    if st.button("Redigér profil", width="stretch"): navigate("edit_profile")
    metric_grid([
        ("Liga-score", f"{stats['league_score']:.1f}", f"{format_score_change(stats['latest_change'])} senest"),
        ("Rangering", f"#{rank}" if rank else "Unranked", None),
        ("Ligaspil", stats["eligible_games"], None),
        ("Højeste liga-score", f"{stats['highest_league_score']:.1f}", None),
    ], delta_tone=score_change_tone(stats["latest_change"]))

    first_fridge = stats["first_koleskabsgame"]
    latest_fridge = stats["latest_koleskabsgame"]
    fridge_detail = (
        f'Første {first_fridge["date"][:10]} · Seneste {latest_fridge["date"][:10]}'
        if first_fridge else "Vind · mindst 125 point · ingen negative runder"
    )
    rounds_detail = (
        f'{stats["round_win_rate"]:.1f}% af {stats["rounds_played"]} registrerede runder · liga #{stats["rounds_won_rank"]}'
        if stats["rounds_played"] else "Afventer spil med gemte rundedata"
    )
    st.subheader("Signaturer")
    st.markdown(f'''<div class="signature-grid">
    <div class="signature-card"><small>Køleskabsgames</small><strong>{stats["koleskabsgames"]}</strong><p>{html.escape(fridge_detail)}</p></div>
    <div class="signature-card"><small>Vundne runder</small><strong>{stats["rounds_won"]}</strong><p>{html.escape(rounds_detail)}</p></div>
    </div>''', unsafe_allow_html=True)
    tabs = st.tabs(["Statistik", "Spilhistorik"])
    with tabs[0]:
        groups = [
            ("Resultater", {
                "Sejre": stats["wins"], "Win rate": f"{stats['win_rate']:.1f}%",
                "Top-2": f"{stats['top2_rate']:.1f}%", "Gennemsnitsplacering": f"{stats['average_placement']:.2f}",
                "Sidstepladser": stats["last_places"],
            }),
            ("Point", {
                "Bedste score": stats["best_score"], "Point pr. spil": f"{stats['average_score']:.1f}",
                "Samlet score": stats["total_score"],
            }),
            ("Streaks", {
                "Aktuel winstreak": stats["current_streak"], "Længste winstreak": stats["longest_win_streak"],
                "Længst uden sidsteplads": stats["longest_without_last"],
            }),
            ("Shots", {"Givet": stats["shots_given"], "Modtaget": stats["shots_received"]}),
        ]
        for heading, values in groups:
            st.subheader(heading)
            metric_grid([(label, value, None) for label, value in values.items()])
    with tabs[1]: render_player_history(stats)


def render_player_history(stats: dict) -> None:
    if not stats["history"]: st.info("Ingen gennemførte spil endnu."); return
    for entry in reversed(stats["history"]):
        league_text = (
            f'{entry["league_score_before"]:.1f} → <strong>{entry["league_score_after"]:.1f}</strong> · præstation {entry["performance_score"]:.1f}'
            if entry["league_score_eligible"] else "Tæller ikke til liga-score"
        )
        st.markdown(f'''<div class="history-card"><span><small>Dato</small><br>{entry["date"][:16].replace("T", " ")}</span>
        <span><small>Placering</small><br><strong>#{entry["placement"]}</strong></span>
        <span><small>Score</small><br>{entry["score"]} point</span>
        <span><small>Liga-score</small><br>{league_text}</span></div>''', unsafe_allow_html=True)
        if st.button("Se spil", key=f"history_{entry['game_id']}", width="stretch"): open_game(entry["game_id"])


def edit_profile_screen() -> None:
    navigation(); admin_gate(); data = load_data(); player = next(p for p in data["players"] if p["id"] == st.session_state.selected_player_id)
    st.title(f"Redigér {player['name']}")
    with st.form("profile_name"):
        name = st.text_input("Spillernavn", player["name"])
        if st.form_submit_button("Gem navn", type="primary"):
            try: update_player(player["id"], name); st.success("Navnet er gemt."); st.rerun()
            except ValueError as error: st.error(str(error))
    st.subheader("Avatar")
    uploaded = st.file_uploader("JPG, PNG eller WebP · maks. 2 MB", type=["jpg", "jpeg", "png", "webp"])
    if uploaded:
        try:
            normalized_avatar = normalize_avatar_upload(uploaded.getvalue(), uploaded.type)
        except ValueError as error:
            st.error(str(error))
        else:
            st.image(normalized_avatar, width=180, caption="Forhåndsvisning")
            if st.button("Gem avatar", type="primary"):
                try: save_avatar(player["id"], normalized_avatar, uploaded.type); st.success("Avataren er gemt."); st.rerun()
                except ValueError as error: st.error(str(error))
    if player.get("avatar") and st.button("Fjern avatar"):
        remove_avatar(player["id"]); st.rerun()
    if st.button("← Profil"): navigate("player_profile")


def recent_games_screen() -> None:
    navigation(); st.title("Spilhistorik"); render_recent_games(load_data(), show_heading=False)


def render_recent_games(data: dict, limit: int = 10, show_heading: bool = True) -> None:
    games = sorted(data["games"], key=lambda game: (game["completed_at"], game["id"]), reverse=True)[:limit]
    players = {player["id"]: player for player in data["players"]}
    if show_heading: st.subheader("Seneste spil")
    if not games: st.info("Ingen konkurrencespil er gennemført endnu."); return
    for game in games:
        results = sorted(game["results"], key=lambda result: (result["placement"], -result["score"]))
        winners = [players[result["player_id"]]["name"] for result in results if result["placement"] == 1]
        winner_text = " & ".join(winners)
        status = "Kvalificeret" if results[0]["league_score_eligible"] else "Tæller ikke til Liga-score"
        status_class = "eligible" if results[0]["league_score_eligible"] else "excluded"
        podium = "".join(
            f'<span><b>#{result["placement"]}</b> {html.escape(players[result["player_id"]]["name"])}'
            f'<strong>{result["score"]}</strong></span>'
            for result in results[:3]
        )
        with st.container(key=f"game_card_{game['id']}"):
            st.markdown(f'''<div class="recent-game-card"><div class="recent-game-head">
            <time>{game["completed_at"][:10]}</time><span class="game-status {status_class}">{status}</span></div>
            <div class="recent-game-winner">🏆 {html.escape(winner_text)}</div>
            <small>{len(results)} spillere</small><div class="recent-game-podium">{podium}</div></div>''', unsafe_allow_html=True)
            if st.button("Åbn spildetaljer", key=f"open_recent_{game['id']}", width="stretch"):
                open_game(game["id"])


def render_game_analysis(data: dict, game: dict, key_prefix: str, profile_links: bool = False) -> None:
    raw_players = {player["id"]: player for player in data["players"]}
    board = leaderboard(data)
    players = {row["id"]: row for row in board["official"] + board["provisional"]}
    for player_id, player in raw_players.items():
        players.setdefault(player_id, player)
    results = sorted(game["results"], key=lambda result: (result["placement"], -result["score"]))
    winner = players[results[0]["player_id"]]
    score_spread = results[0]["score"] - results[-1]["score"]
    st.caption(f'{game["completed_at"][:16].replace("T", " ")} · {game.get("location") or "Ingen lokation"}')
    metric_grid([
        ("Vinder", winner["name"], None), ("Spillere", len(results), None),
        ("Vinderscore", results[0]["score"], None), ("Scoreafstand", score_spread, None),
    ])
    st.subheader("Slutstilling")
    for result in results:
        player = players[result["player_id"]]
        performance = f'{result["performance_score"]:.1f} præstation' if result["league_score_eligible"] else "Ikke kvalificeret"
        card = f'''<div class="rank-card"><div class="rank-head"><div class="rank-number">#{result["placement"]}</div>{avatar_markup(player, 44)}
        <div class="rank-name">{identity_markup(player)}</div><div class="rank-score"><strong>{result["score"]}</strong><small>{performance}</small></div></div>
        <div class="rank-stats"><span>Liga-score før<strong>{result["league_score_before"]:.1f}</strong></span><span>Liga-score efter<strong>{result["league_score_after"]:.1f}</strong></span>
        <span>Kvalificerede spil<strong>{result["eligible_game_number"]}</strong></span></div></div>'''
        if profile_links:
            with st.container(key=f"player_card_{key_prefix}_{player['id']}"):
                st.markdown(card, unsafe_allow_html=True)
                if st.button(f'Åbn profil for {player["name"]}', key=f"open_{key_prefix}_{player['id']}", width="stretch"):
                    open_player(player["id"])
        else:
            st.markdown(card, unsafe_allow_html=True)

    if not results[0]["league_score_eligible"]:
        st.info("Spillet har færre end fem deltagere og tæller derfor ikke til liga-score.")
    if not game.get("rounds"):
        st.info("Der er ingen gemt rundehistorik for dette spil.")
        return

    clean_rounds = [
        {"Kort": round_["cards"], **{players[player_id]["name"]: value for player_id, value in round_.items() if player_id != "cards"}}
        for round_ in game["rounds"]
    ]
    st.subheader("Runder")
    st.dataframe(clean_rounds, width="stretch", hide_index=True)
    shot_rows = []
    for result in results:
        player_id = result["player_id"]
        shots = [shots_from_score(round_[player_id]) for round_ in game["rounds"] if player_id in round_]
        shot_rows.append({"Spiller": players[player_id]["name"], "Givet": sum(item["given"] for item in shots),
                          "Modtaget": sum(item["received"] for item in shots)})
    st.subheader("Shots")
    st.dataframe(shot_rows, width="stretch", hide_index=True)
    st.caption(f'Liga-score: {game.get("league_score_algorithm", "—")} v{game.get("league_score_version", "—")} · Neutralværdi: {game.get("neutral_score", 7)}')


def game_detail_screen() -> None:
    navigation(); data = load_data(); game = next((item for item in data["games"] if item["id"] == st.session_state.selected_game_id), None)
    if not game: st.error("Spillet findes ikke."); return
    st.title("Spildetaljer")
    render_game_analysis(data, game, f"detail_{game['id']}", profile_links=True)


def record_value_text(record: dict) -> str:
    value = f"{record['value']:.1f}" if isinstance(record["value"], float) else str(record["value"])
    unit = record.get("unit", "")
    if record["value"] == 1:
        unit = {
            "sejre": "sejr", "Køleskabsgames": "Køleskabsgame", "runder": "runde",
            "sejre i træk": "sejr i træk",
        }.get(unit, unit)
    return f"{value} {unit}".strip()


def hall_of_fame_screen() -> None:
    navigation(); st.title("Hall of Fame"); data = load_data()
    if not data["games"]:
        st.info("Rekorderne åbner efter det første konkurrencespil.")
        return
    records = hall_of_fame(data)
    if not records: st.info("Ingen rekorder endnu."); return
    board = leaderboard(data)
    current_players = {row["id"]: row for row in board["official"] + board["provisional"]}
    for index, record in enumerate(records):
        value = record_value_text(record)
        player_id = record.get("player_id")
        record_player = current_players.get(player_id, {"name": record["name"]})
        holder = identity_text(record_player) if player_id else record["name"]
        expanded = index in st.session_state.expanded_record_ids
        icon = "▾" if expanded else "▸"
        summary = f'{icon} {record["title"]} · {holder} · {value}'
        if st.button(summary, key=f"record_summary_{index}", width="stretch"):
            if expanded: st.session_state.expanded_record_ids.remove(index)
            else: st.session_state.expanded_record_ids.append(index)
            st.rerun()
        if not expanded:
            continue
        achieved = record["date"][:10] if record.get("date") else "Ikke opnået endnu"
        st.markdown(f'''<div class="record-card"><h3>{html.escape(record["title"])}</h3>
        <strong>{identity_markup(record_player) if player_id else html.escape(record["name"])}</strong>
        <span>{html.escape(value)}</span><small>Opnået: {achieved}</small></div>''', unsafe_allow_html=True)
        if record.get("related"):
            metric_grid([(item["label"], item["value"], None) for item in record["related"]])
        actions = st.columns(2)
        if player_id and actions[0].button("Se profil", key=f"hof_{index}", width="stretch"):
            open_player(player_id)
        if record.get("game_id") and actions[1].button("Se rekordspil", key=f"hof_game_{index}", width="stretch"):
            open_game(record["game_id"])


def admin_screen() -> None:
    navigation()
    st.title("Administration")
    admin_gate()
    st.warning("Ændringer her påvirker det permanente leaderboard.")
    data = load_data()
    with st.expander("Spilregler", expanded=True):
        with st.form("admin_rules"):
            neutral_score = st.number_input(
                "Neutralværdi", min_value=0, max_value=10,
                value=int(data["settings"]["neutral_score"]),
                help="Point for 0 stik ved et bud på 0. Gælder nye spil.",
            )
            if st.form_submit_button("Gem regler", type="primary"):
                update_settings(int(neutral_score))
                st.success(f"Neutralværdien er nu {int(neutral_score)}.")
                st.rerun()
    with st.expander("Tilføj spiller", expanded=True):
        with st.form("admin_add_player", clear_on_submit=True):
            name = st.text_input("Spillernavn")
            if st.form_submit_button("Tilføj spiller", type="primary"):
                try:
                    add_player(name)
                    st.success(f"{name.strip()} er tilføjet.")
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))

    data = load_data()
    st.subheader("Spillere")
    for player in data["players"]:
        cols = st.columns([4, 1])
        cols[0].write(player["name"])
        if cols[1].button("Redigér", key=f"admin_player_{player['id']}"):
            st.session_state.selected_player_id = player["id"]
            navigate("edit_profile")

    st.subheader("Slet gennemført spil")
    games = sorted(data["games"], key=lambda game: game["completed_at"], reverse=True)
    players = {player["id"]: player for player in data["players"]}
    if not games:
        st.info("Der er ingen spil at slette.")
    for game in games:
        names = ", ".join(players[result["player_id"]]["name"] for result in game["results"])
        with st.expander(f"{game['completed_at'][:16].replace('T', ' ')} · {names}"):
            confirm = st.checkbox("Jeg forstår, at spillet slettes permanent", key=f"confirm_delete_{game['id']}")
            if st.button("Slet spil", key=f"delete_{game['id']}", disabled=not confirm):
                delete_game(game["id"])
                st.success("Spillet er slettet, og liga-score-historikken er genberegnet.")
                st.rerun()


def start_game(players: list, max_cards: int, competition: bool) -> None:
    neutral_score = int(load_data()["settings"]["neutral_score"])
    game = Game(max_cards=max_cards, neutral_score=neutral_score); id_map = {}
    for player in players:
        game_player = game.add_player(player["name"] if competition else player)
        if competition: id_map[game_player.id] = player["id"]
    st.session_state.game = game; st.session_state.competition_ids = id_map
    st.session_state.current_player_idx = 0; st.session_state.competition_saved = False
    st.session_state.competition_created_in_session = False
    st.session_state.score_history = []
    st.session_state.active_game_id = uuid.uuid4().hex; st.session_state.phase = "playing"
    st.session_state.scroll_to_top = True
    save_active_game_draft(); st.rerun()


def temporary_setup_screen() -> None:
    navigation(); st.title("Midlertidigt spil"); names = st.session_state.player_names
    for i in range(len(names)):
        with st.container(key=f"setup_player_{i}"):
            cols = st.columns([5, 1]); names[i] = cols[0].text_input(
                f"Spiller {i + 1}", value=names[i], key=f"name_{i}", max_chars=80,
            )
            if len(names) > 2 and cols[1].button("Fjern", key=f"remove_{i}", width="stretch"): names.pop(i); st.rerun()
    if len(names) < 7 and st.button("+ Tilføj spiller"): names.append(""); st.rerun()
    max_cards = st.number_input("Højeste antal kort", 1, 13, 7, key="temporary_cards")
    if st.button("Start spillet", type="primary", width="stretch"):
        valid = [name.strip() for name in names if name.strip()]
        if len(valid) < 2 or len({name.casefold() for name in valid}) != len(valid): st.error("Vælg mindst to spillere med forskellige navne.")
        else: st.session_state.game_type = "temporary"; start_game(valid, int(max_cards), False)


def simulation_controls(data: dict, selected: list[str], max_cards: int) -> None:
    """Render the isolated development-only preview, confirmation and cleanup flow."""
    by_id = {player["id"]: player for player in data["players"]}
    with st.expander("TEST ONLY · Simulér testspil"):
        st.warning("Kun testdata. Spillet gemmes først efter bekræftelse.")
        count = st.number_input("Antal simulerede spil", 1, 20, 1, key="simulation_count")
        seed_text = st.text_input("Tilfældigheds-seed (valgfri)", key="simulation_seed")
        if st.button("Generér test-preview", key="generate_simulation", width="stretch"):
            try:
                seed = int(seed_text) if seed_text.strip() else None
                st.session_state.simulation_preview = generate_simulated_games(
                    data, selected, count=int(count), seed=seed, max_cards=int(max_cards),
                )
                st.rerun()
            except (ValueError, PermissionError) as error:
                st.error(str(error))

        previews = st.session_state.simulation_preview
        if previews:
            st.markdown("#### Simulated test game · preview")
            for index, game in enumerate(previews, 1):
                ordered = sorted(game["scores"], key=lambda player_id: (game["placements"][player_id], -game["scores"][player_id]))
                result_text = " · ".join(
                    f'{game["placements"][player_id]}. {by_id[player_id]["name"]} {game["scores"][player_id]}'
                    for player_id in ordered
                )
                fridge_names = ", ".join(by_id[player_id]["name"] for player_id in game["koleskab_player_ids"])
                st.markdown(f"**Testspil {index}:** {result_text}")
                st.caption(f"Køleskabsgame: {fridge_names or 'Nej'}")
            confirm, cancel = st.columns(2)
            if confirm.button("Bekræft og gem", type="primary", key="save_simulation", width="stretch"):
                try:
                    saved = save_simulated_games(previews)
                    st.session_state.simulation_preview = []
                    st.success(f"{len(saved)} simulerede testspil er gemt gennem den normale liga-score-pipeline.")
                    st.rerun()
                except (ValueError, PermissionError) as error:
                    st.error(str(error))
            if cancel.button("Annuller", key="cancel_simulation", width="stretch"):
                st.session_state.simulation_preview = []
                st.rerun()

        simulated = [game for game in load_data()["games"] if game.get("source") == "simulation"]
        if simulated:
            st.divider()
            st.markdown("#### TEST ONLY · Oprydning")
            game_id = st.selectbox(
                "Simuleret spil", [game["id"] for game in reversed(simulated)],
                format_func=lambda value: next(game["completed_at"][:16].replace("T", " ") for game in simulated if game["id"] == value),
            )
            one, all_games = st.columns(2)
            if one.button("Slet valgt testspil", key="delete_one_simulation", width="stretch"):
                try:
                    delete_simulated_game(game_id)
                    st.success("Testspillet er slettet, og liga-score-historikken er genberegnet.")
                    st.rerun()
                except (ValueError, PermissionError) as error:
                    st.error(str(error))
            remove_all = all_games.checkbox("Bekræft alle", key="confirm_delete_simulations")
            if all_games.button("Slet alle testspil", key="delete_all_simulations", disabled=not remove_all, width="stretch"):
                try:
                    deleted = delete_all_simulated_games()
                    st.success(f"{deleted} simulerede spil er slettet. Rigtige spil blev ikke berørt.")
                    st.rerun()
                except PermissionError as error:
                    st.error(str(error))


def competition_setup_screen() -> None:
    navigation(); st.title("Nyt konkurrencespil"); data = load_data(); by_id = {p["id"]: p for p in data["players"]}
    selected = st.multiselect("Vælg spillere", list(by_id), format_func=lambda pid: by_id[pid]["name"])
    location = st.text_input("Lokation (valgfri)", key="game_location")
    max_cards = st.number_input("Højeste antal kort", 1, 13, 7, key="competition_cards")
    if st.button("Start konkurrencespil", type="primary"):
        if not MIN_COMPETITION_PLAYERS <= len(selected) <= MAX_COMPETITION_PLAYERS:
            st.error(f"Vælg mellem {MIN_COMPETITION_PLAYERS} og {MAX_COMPETITION_PLAYERS} spillere.")
        else: st.session_state.game_type = "competition"; st.session_state.location = location; start_game([by_id[pid] for pid in selected], int(max_cards), True)
    if test_mode_enabled() and admin_access_granted():
        simulation_controls(data, selected, int(max_cards))


def submit_score(score: int) -> None:
    game = st.session_state.game
    round_idx = game.current_round_index
    player_idx = st.session_state.current_player_idx
    player = game.players[player_idx]
    st.session_state.score_history.append({"round": round_idx, "player_id": player.id, "player_idx": player_idx})
    game.record_score(player.id, score)
    if player_idx + 1 < len(game.players):
        st.session_state.current_player_idx += 1
    else:
        st.session_state.current_player_idx = 0
        if not game.advance_round():
            st.session_state.phase = "finished"
            st.session_state.scroll_to_top = True
    save_active_game_draft()
    st.rerun()


def undo_last_score() -> None:
    if not st.session_state.score_history:
        return
    if st.session_state.competition_saved:
        if not st.session_state.competition_created_in_session:
            st.error("Et allerede gemt spil kan kun rettes fra Administration.")
            return
        delete_game(st.session_state.active_game_id)
        st.session_state.competition_saved = False
        st.session_state.competition_created_in_session = False
    entry = st.session_state.score_history.pop()
    game = st.session_state.game
    game.remove_score(entry["player_id"], entry["round"])
    st.session_state.current_player_idx = entry["player_idx"]
    st.session_state.phase = "playing"
    st.session_state.scroll_to_top = True
    save_active_game_draft()
    st.rerun()


def cancel_game() -> None:
    clear_active_game_draft()
    st.session_state.game = None
    st.session_state.score_history = []
    st.session_state.competition_saved = False
    st.session_state.competition_created_in_session = False
    st.session_state.active_game_id = None
    st.session_state.phase = "home"
    st.session_state.scroll_to_top = True
    st.rerun()


def playing_screen() -> None:
    game = st.session_state.game; round_idx = game.current_round_index; round_ = game.rounds[round_idx]
    player_idx = st.session_state.current_player_idx; player = game.players[player_idx]
    if st.session_state.game_type == "competition":
        data = load_data()
        board = leaderboard(data)
        players_by_stable_id = {row["id"]: row for row in board["official"] + board["provisional"]}
        player_rows = {
            game_player.id: players_by_stable_id[st.session_state.competition_ids[game_player.id]]
            for game_player in game.players
        }
    else:
        player_rows = {game_player.id: {"name": game_player.name, "avatar": None} for game_player in game.players}
    st.progress((round_idx * len(game.players) + player_idx) / (len(game.rounds) * len(game.players)))
    st.markdown(f"### Runde {round_idx + 1}/{len(game.rounds)} · {round_.cards} kort")
    with st.container(key="score_back"):
        if st.button("↶ Fortryd sidste score", disabled=not st.session_state.score_history, width="stretch"):
            undo_last_score()
    player_display = player_rows[player.id]
    st.markdown(f'''<div class="score-player-head">{avatar_markup(player_display, 82)}<div><div class="eyebrow">Næste spiller</div>
    <div class="score-player-name" role="heading" aria-level="1">{identity_markup(player_display)}</div><span class="muted">Vælg rundens score</span></div></div>''', unsafe_allow_html=True)

    valid = round_.valid_scores()
    positives = [score for score in valid if score >= 11]
    negatives = [score for score in valid if score < 0]
    st.caption("GIV SHOTS")
    with st.container(key="positive_scores"):
        cols = st.columns(min(3, len(positives)))
        for index, score in enumerate(positives):
            if cols[index % len(cols)].button(f"+{score}", key=f"score_{round_idx}_{player.id}_{score}", width="stretch"): submit_score(score)
    with st.container(key="neutral_score"):
        neutral = game.neutral_score
        if st.button(f"{neutral} · neutral", key=f"score_{round_idx}_{player.id}_{neutral}", width="stretch"): submit_score(neutral)
    st.caption("DRIK SHOTS")
    with st.container(key="negative_scores"):
        cols = st.columns(min(3, len(negatives)))
        for index, score in enumerate(negatives):
            if cols[index % len(cols)].button(str(score), key=f"score_{round_idx}_{player.id}_{score}", width="stretch"): submit_score(score)

    totals = game.totals()
    st.subheader("Stillingen")
    standings_html = "".join(
        f'<div class="standing-row"><strong>{index}. {identity_markup(player_rows[standing.id])}</strong><span>{totals[standing.id]} point</span></div>'
        for index, standing in enumerate(game.standings(), 1)
    )
    st.markdown(standings_html, unsafe_allow_html=True)
    with st.expander("Afslut spil"):
        st.caption("Det igangværende spil bliver ikke gemt.")
        if st.button("Afslut uden at gemme", width="stretch"): cancel_game()


def finished_screen() -> None:
    game = st.session_state.game; totals = game.totals(); standings = game.standings()
    if st.session_state.game_type == "competition" and not st.session_state.competition_saved:
        id_map = st.session_state.competition_ids
        scores = {id_map[player.id]: totals[player.id] for player in game.players}
        rounds = [{"cards": round_.cards, **{id_map[pid]: score for pid, score in round_.scores.items()}} for round_ in game.rounds]
        saved, created = record_game(
            scores, game_id=st.session_state.active_game_id, rounds=rounds,
            location=st.session_state.get("location"), neutral_score=game.neutral_score,
            return_created=True,
        )
        st.session_state.competition_saved = True
        st.session_state.competition_created_in_session = created
        st.session_state.selected_game_id = saved["id"]
    if st.session_state.game_type == "competition":
        board = leaderboard(load_data())
        players_by_stable_id = {row["id"]: row for row in board["official"] + board["provisional"]}
        player_rows = {
            game_player.id: players_by_stable_id[st.session_state.competition_ids[game_player.id]]
            for game_player in game.players
        }
    else:
        player_rows = {game_player.id: {"name": game_player.name} for game_player in game.players}
    st.title("Spillet er slut")
    st.header(f"🏆 {identity_text(player_rows[standings[0].id])} vinder")
    standings_html = "".join(
        f'<div class="standing-row"><strong>{index}. {identity_markup(player_rows[player.id])}</strong><span>{totals[player.id]} point</span></div>'
        for index, player in enumerate(standings, 1)
    )
    st.markdown(standings_html, unsafe_allow_html=True)
    with st.container(key="score_back"):
        if st.button("↶ Fortryd sidste score", width="stretch"): undo_last_score()
    if st.session_state.game_type == "competition" and st.button("Se spildetaljer"):
        clear_active_game_draft(); navigate("game_detail")
    if st.button("Til forsiden"):
        clear_active_game_draft(); navigate("home")


SCREENS = {
    "home": home_screen, "leaderboard": leaderboard_screen, "players": players_screen, "player_profile": player_profile_screen,
    "edit_profile": edit_profile_screen, "recent_games": recent_games_screen, "game_detail": game_detail_screen,
    "hall_of_fame": hall_of_fame_screen, "admin": admin_screen, "temporary_setup": temporary_setup_screen,
    "competition_setup": competition_setup_screen, "playing": playing_screen, "finished": finished_screen,
}
authentication_gate()
restore_active_game_draft()
scroll_slot = st.empty()
if st.session_state.pop("scroll_to_top", False):
    with scroll_slot.container():
        st.iframe(
            """<style>html,body{margin:0;background:transparent;overflow:hidden}</style><script>
            const main = window.parent.document.querySelector('[data-testid="stMain"]');
            if (main) {
                requestAnimationFrame(() => main.scrollTo({top: 0, left: 0, behavior: 'auto'}));
                setTimeout(() => main.scrollTo({top: 0, left: 0, behavior: 'auto'}), 50);
            }
            </script>""",
            height=1,
            tab_index=-1,
        )
SCREENS.get(st.session_state.phase, home_screen)()