import streamlit as st
import folium
from streamlit_folium import st_folium
from streamlit_autorefresh import st_autorefresh
from streamlit_geolocation import streamlit_geolocation
from streamlit_searchbox import st_searchbox
from datetime import datetime
import time as time_lib
import requests

# Importando seus novos módulos
import api_google
import api_sptrans
import api_tfl

# ==========================================
# 1. FUNÇÕES AUXILIARES
# ==========================================
def decode_poly(p):
    index, lat, lng = 0, 0, 0
    coords = []
    while index < len(p):
        for unit in ['lat', 'lng']:
            shift, result = 0, 0
            while True:
                byte = ord(p[index]) - 63
                index += 1
                result |= (byte & 0x1f) << shift
                shift += 5
                if not byte >= 0x20: break
            change = ~(result >> 1) if (result & 1) else (result >> 1)
            if unit == 'lat': lat += change
            else: lng += change
        coords.append([lat/100000.0, lng/100000.0])
    return coords

# ==========================================
# 2. CONFIGURAÇÕES, CHAVES E IDENTIDADE VISUAL
# ==========================================
TOKEN_SPTRANS = st.secrets.get("TOKEN_SPTRANS", "")
CHAVE_GOOGLE = st.secrets.get("CHAVE_GOOGLE", "")

st.set_page_config(page_title="BusRadar Pro", layout="wide", page_icon="🚌")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .main { background-color: #f0f4f8; }
    
    .stButton>button {
        border-radius: 10px; background: linear-gradient(135deg, #004a99, #0066cc);
        color: white; font-weight: 600; width: 100%; border: none;
        box-shadow: 0 4px 12px rgba(0,74,153,0.2); transition: 0.2s;
    }
    .stButton>button:hover { transform: translateY(-1px); box-shadow: 0 6px 15px rgba(0,74,153,0.3); }
    
    .instrucao-passo {
        padding: 12px 16px; border-left: 4px solid #004a99; background: white;
        margin-bottom: 8px; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        font-size: 14px;
    }
    
    .horario-pills {
        display: inline-block; background-color: #f1f3f5; border-radius: 4px;
        padding: 2px 8px; margin: 2px; font-size: 11px; border: 1px solid #dee2e6;
        color: #333; font-family: monospace;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 3. GESTÃO DE ESTADO E CARREGAMENTO DE DADOS
# ==========================================
dados_paradas, dados_horarios, dados_trajetos = api_sptrans.carregar_dados_locais()
sessao_sptrans = api_sptrans.criar_sessao(TOKEN_SPTRANS)

if 'rota_ativa' not in st.session_state: st.session_state['rota_ativa'] = None
if 'origem_sel' not in st.session_state: st.session_state['origem_sel'] = None
if 'destino_sel' not in st.session_state: st.session_state['destino_sel'] = None

# ==========================================
# 4. SIDEBAR E NAVEGAÇÃO
# ==========================================
with st.sidebar:
    st.markdown('<p style="font-size:24px; font-weight:800; color:white;">🚌 BusRadar Pro</p>', unsafe_allow_html=True)
    st.caption("v7.5 · Autocompletar & Bug Fixado")
    st.divider()
    
    menu = st.radio("Navegação:", ["🗺️ Planejador", "🚌 Monitor", "📍 Radar", "🇬🇧 Londres"])
    
    st.divider()
    gps = streamlit_geolocation()
    lat_u, lon_u = (gps['latitude'], gps['longitude']) if gps and gps.get('latitude') else (None, None)
    if lat_u: 
        st.success("🛰️ GPS Conectado")
    else: 
        st.warning("📡 Aguardando sinal de satélite...")
    
    st.divider()
    st.info("Dados locais carregados.")

# ==========================================
# PÁGINA 1: PLANEJADOR (COM AUTOCOMPLETAR)
# ==========================================
if menu == "🗺️ Planejador":
    st.subheader("Para onde vamos hoje?")
    
    # --- Função adaptadora para o Autocompletar ---
    def pesquisar_lugares_auto(termo: str):
        if not termo or len(termo) < 3:
            return []
        opcoes = api_google.buscar_lugares_google(termo, CHAVE_GOOGLE)
        if not opcoes:
            return []
        # Retorna a tupla (Texto Visível, Dicionário de Dados com Coord)
        return [(nome, {"nome": nome, "coord": f"{dados['lat']},{dados['lng']}"}) for nome, dados in opcoes.items()]
    # ----------------------------------------------
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.markdown("**1. Ponto de Partida**")
        t_o = st.radio("Origem:", ["📍 Meu GPS", "🔍 Digitar Endereço"], horizontal=True)
        
        if t_o == "📍 Meu GPS":
            if lat_u:
                st.session_state['origem_sel'] = {"nome": "Sua localização atual", "coord": f"{lat_u},{lon_u}"}
                st.success("📍 GPS selecionado!")
            else: 
                st.warning("GPS não detectado.")
                
        elif t_o == "🔍 Digitar Endereço":
            selecao_o = st_searchbox(
                pesquisar_lugares_auto, 
                key="box_origem", 
                placeholder="Ex: Metrô Ana Rosa..."
            )
            if selecao_o:
                st.session_state['origem_sel'] = selecao_o

        if st.session_state.get('origem_sel') and t_o == "🔍 Digitar Endereço":
            st.info(f"Origem: {st.session_state['origem_sel']['nome']}")
    
    with col_b:
        st.markdown("**2. Destino**")
        t_d = st.radio("Destino:", ["🔍 Digitar Endereço", "📍 Meu GPS"], horizontal=True, key="radio_destino")

        if t_d == "📍 Meu GPS":
            if lat_u:
                st.session_state['destino_sel'] = {"nome": "Sua localização atual (destino)", "coord": f"{lat_u},{lon_u}"}
                st.success("📍 GPS selecionado como destino!")
            else:
                st.warning("GPS não detectado.")
        else:
            selecao_d = st_searchbox(
                pesquisar_lugares_auto, 
                key="box_destino", 
                placeholder="Ex: Aeroporto Congonhas..."
            )
            if selecao_d:
                st.session_state['destino_sel'] = selecao_d

        if st.session_state.get('destino_sel') and t_d == "🔍 Digitar Endereço":
            st.info(f"Destino: {st.session_state['destino_sel']['nome']}")

    # ==========================
    # BOTÃO DE ROTA (CORREÇÃO BUG 12:36)
    # ==========================
    if st.session_state.get('origem_sel') and st.session_state.get('destino_sel'):
        st.divider()
        
        with st.expander("⚙️ Opções Avançadas de Trajeto"):
            col_m, col_p, col_h1, col_h2 = st.columns([2, 2, 2, 2])
            with col_m:
                modo_trans = st.selectbox("Transporte:", ["transit", "walking", "driving"], format_func=lambda x: "🚌 Ônibus/Metrô" if x=="transit" else ("🚶 A pé" if x=="walking" else "🚗 Carro"))
            with col_p:
                prioridade = st.selectbox("Prioridade:", ["best_guess", "fewer_transfers", "less_walking"], format_func=lambda x: "⚡ Mais Rápido" if x=="best_guess" else ("🔄 Menos Trocas" if x=="fewer_transfers" else "🚶 Menos Caminhada"))
            with col_h1:
                tipo_h = st.selectbox("Horário:", ["Sair Agora", "Partida às...", "Chegada às..."])
            with col_h2:
                if tipo_h != "Sair Agora":
                    data_escolhida = st.date_input("Data:", value=datetime.today().date())
                    hora_escolhida = st.time_input("Hora:", value=datetime.now().time())
                else:
                    data_escolhida, hora_escolhida = None, None

        if st.button("🚀 TRAÇAR ROTA AGORA", type="primary"):
            with st.spinner("Consultando Google Maps..."):
                o = st.session_state['origem_sel']['coord']
                d = st.session_state['destino_sel']['coord']
                
                url = "https://maps.googleapis.com/maps/api/directions/json"
                
                parametros = {
                    "origin": str(o).strip(),
                    "destination": str(d).strip(),
                    "mode": modo_trans,
                    "language": "pt-BR",
                    "key": CHAVE_GOOGLE
                }
                
                if modo_trans == "transit":
                    parametros["transit_routing_preference"] = prioridade
                
                if tipo_h != "Sair Agora" and hora_escolhida and data_escolhida:
                    dt = datetime.combine(data_escolhida, hora_escolhida)
                    ts_calc = int(time_lib.mktime(dt.timetuple()))
                    
                    if tipo_h == "Partida às..." and ts_calc < int(time_lib.time()):
                        st.error("⚠️ O horário de partida não pode estar no passado! Ajuste a data ou a hora.")
                        st.stop()
                        
                    if tipo_h == "Partida às...": parametros["departure_time"] = ts_calc
                    else: parametros["arrival_time"] = ts_calc
                
                try:
                    resp = requests.get(url, params=parametros).json()
                    if resp.get('status') == 'OK': 
                        st.session_state['rota_ativa'] = resp['routes'][0]
                        st.rerun() 
                    else: 
                        st.error(f"O Google recusou a rota. Status: {resp.get('status')}")
                except Exception as e:
                    st.error(f"Erro de conexão com o Google: {e}")

    # EXIBIÇÃO DO MAPA E INSTRUÇÕES
    if st.session_state.get('rota_ativa'):
        st.divider()
        r = st.session_state['rota_ativa']
        leg = r['legs'][0]
        st.success(f"⏱️ Tempo: **{leg['duration']['text']}** | 🏁 Chegada: **{leg.get('arrival_time', {}).get('text', 'N/D')}**")
        
        c1, c2 = st.columns([4, 6])
        with c1:
            for s in leg['steps']:
                txt = s['html_instructions'].replace('<b>', '**').replace('</b>', '**')
                st.markdown(f'<div class="instrucao-passo">{txt}</div>', unsafe_allow_html=True)
            if st.button("🗑️ Nova Busca"):
                st.session_state['rota_ativa'] = None
                st.session_state['origem_sel'] = None
                st.session_state['destino_sel'] = None
                st.rerun()
        with c2:
            pts = decode_poly(r['overview_polyline']['points'])
            m = folium.Map(location=pts[0], zoom_start=14, tiles='CartoDB Positron')
            folium.PolyLine(pts, color="#004a99", weight=6, opacity=0.8).add_to(m)
            folium.Marker(pts[0], icon=folium.Icon(color='green', icon='play')).add_to(m)
            folium.Marker(pts[-1], icon=folium.Icon(color='red', icon='flag')).add_to(m)
            st_folium(m, width=700, height=500, key="mapa_planejador")

# ==========================================
# PÁGINA 2: MONITOR DE FROTA
# ==========================================
elif menu == "🚌 Monitor":
    st.subheader("🚌 Radar da Linha em Tempo Real")
    lin_id = st.text_input("🔍 Número da Linha (ex: 675A):", key="mon_in")
    
    if lin_id and TOKEN_SPTRANS:
        res_l = api_sptrans.buscar_linha(sessao_sptrans, lin_id)
        
        if res_l:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in res_l}
            l_sel = opcoes[st.selectbox("Escolha o sentido:", list(opcoes.keys()))]
            
            sl_idx = l_sel['sl'] - 1
            chave_h = f"{l_sel['lt']}-{l_sel['tl']}-{sl_idx}"
            ch_traj = f"{l_sel['lt']}-{l_sel['tl']}-{l_sel['sl']}"
            
            if chave_h in dados_horarios:
                with st.expander("📅 Horários Programados (Saídas)"):
                    prog = dados_horarios[chave_h]
                    cu, cs, cd = st.columns(3)
                    for col, dia, tit in zip([cu, cs, cd], ["Útil", "Sábado", "Domingo"], ["📅 Úteis", "🌅 Sábados", "⛪ Domingos"]):
                        with col:
                            st.markdown(f"**{tit}**")
                            h_l = prog.get(dia, [])
                            if h_l: st.markdown("".join([f'<span class="horario-pills">{h}</span>' for h in h_l]), unsafe_allow_html=True)
                            else: st.caption("Sem dados")

            pos = api_sptrans.buscar_posicao_veiculos(sessao_sptrans, l_sel['cl'])
            vs = pos.get('vs', [])
            
            if vs:
                st.metric("🚌 Frota Monitorada", len(vs), delta=f"{sum(1 for v in vs if v.get('a'))} acessíveis")
                m_f = folium.Map(location=[vs[0]['py'], vs[0]['px']], zoom_start=13, tiles='CartoDB Positron')
                if ch_traj in dados_trajetos:
                    folium.PolyLine(dados_trajetos[ch_traj], color="#00A1FF", weight=4, opacity=0.5).add_to(m_f)
                for v in vs:
                    folium.Marker([v['py'], v['px']], icon=folium.Icon(color='blue' if v.get('a') else 'red', icon='bus', prefix='fa')).add_to(m_f)
                st_folium(m_f, width=1000, height=450, key="mapa_frota")
        else: st.error("Linha não encontrada.")

# ==========================================
# PÁGINA 3: RADAR DE ÁREA
# ==========================================
elif menu == "📍 Radar":
    st.subheader("📍 O que está chegando perto de você?")
    if st.checkbox("🔄 Atualizar radar automaticamente (30s)", value=True):
        st_autorefresh(interval=30000, key="refresh_radar")

    if lat_u and dados_paradas:
        pontos = []
        for p in dados_paradas:
            py, px = p.get('py'), p.get('px')
            if not py or not px: continue
            
            try:
                dist = api_sptrans.calcular_distancia_haversine(lat_u, lon_u, float(py), float(px))
                if dist <= 400:
                    pontos.append({'cp': p['cp'], 'np': p['np'], 'dist': int(dist)})
            except (ValueError, TypeError): continue
        
        pontos = sorted(pontos, key=lambda x: x['dist'])[:5]
        if not pontos: st.info("Nenhuma parada encontrada num raio de 400m da sua localização.")
        
        for p in pontos:
            with st.expander(f"🚏 {p['np']} ({p['dist']}m)"):
                try:
                    prev = sessao_sptrans.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Previsao/Parada?codigoParada={p['cp']}", timeout=10).json()
                    if prev and prev.get('p') and 'l' in prev['p']:
                        for lin in prev['p']['l']:
                            st.write(f"🚌 **{lin['c']}** ➔ {lin['vs'][0]['t']} (Prefixo: {lin['vs'][0]['p']})")
                    else: st.caption("Nenhuma previsão agora.")
                except Exception as e:
                    st.caption(f"Erro ao buscar previsão: {e}")
    else: st.warning("Ative o GPS para ver paradas próximas.")

# ==========================================
# PÁGINA 4: LONDRES (TfL)
# ==========================================
elif menu == "🇬🇧 Londres":
    st.title("🇬🇧 London Marathon Prep")
    l_tfl = st.text_input("Número da Linha em Londres (Ex: 15, 390):", key="in_tfl")
    if l_tfl:
        with st.spinner("Consultando TfL API..."):
            df_resultados = api_tfl.buscar_chegadas_tfl(l_tfl)
            if df_resultados is not None:
                st.table(df_resultados)