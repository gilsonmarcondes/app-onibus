import streamlit as st
import pandas as pd  # <--- ESSA É A LINHA QUE ESTÁ FALTANDO!
import requests
import folium
from streamlit_folium import st_folium
from datetime import datetime
import pytz
from streamlit_autorefresh import st_autorefresh
from streamlit_geolocation import streamlit_geolocation
from folium.plugins import LocateControl
import googlemaps

# --- CONFIGURAÇÃO INICIAL ---
st.set_page_config(page_title="D23 Mobilidade", layout="wide")

# --- CONFIGURAÇÃO DE GPS GLOBAL NA SIDEBAR ---
with st.sidebar:
    st.header("📍 Localização em Tempo Real")
    st.write("Ative o GPS para usar as funções de 'Minha Posição'.")
    
    # AGORA SIM: Sem nenhum parâmetro dentro, para não dar erro!
    gps_global = streamlit_geolocation() 
    
    if gps_global and gps_global.get('latitude'):
        st.success("✅ GPS Conectado!")
    else:
        st.warning("Aguardando sinal...")
    st.divider()

# --- O BANHO DE LOJA (INJEÇÃO DE CSS) ---
st.markdown("""
    <style>
    /* Ocultar as marcas do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Estilizar os botões principais */
    div.stButton > button:first-child {
        background-color: #1E1E1E;
        color: white;
        border-radius: 8px;
        border: 1px solid #333333;
        padding: 10px 24px;
        font-weight: bold;
        transition: all 0.3s ease;
        width: 100%;
    }
    div.stButton > button:first-child:hover {
        background-color: #0066cc; /* Azul vibrante ao passar o mouse */
        border-color: #0066cc;
        color: white;
        transform: translateY(-2px); /* Pequeno efeito de elevação */
    }
    </style>
""", unsafe_allow_html=True)

st.title("🌍 D23 Transporte")

# --- AS SUAS CHAVES DE ACESSO ---
TOKEN_SPTRANS = '0ff07fb8ed51fd939f51e92b03571a51fb72aad64fc19586909fd97ac1b6091a'
CHAVE_GOOGLE = 'AIzaSyAtp5jarrnwyy3_JWVfoWGbKlfEd4NjSKk' 
CHAVE_CLIMA = '1fb1b9310c7e1e3192d52f5821b0c1ab'

# --- AS CHAVES INTERNACIONAIS ---
CHAVE_TFL = 'd4fcd31a062a4b1dab6ea40cf1896241'           
CHAVE_BODS = '76765b7adeb5b7e231139229df66db24b94a12d7' # <-- Sua chave do interior da Inglaterra
CHAVE_SCOTLAND = 'CHAVE_TRAVELINE_AQUI'                  
CHAVE_RAIL = 'CHAVE_DARWIN_AQUI' 

gmaps = googlemaps.Client(key=CHAVE_GOOGLE)

def obter_clima_destino(lat, lon, api_key):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}&units=metric&lang=pt_br"
    try:
        resposta = requests.get(url).json()
        if resposta.get('main'):
            temp = round(resposta['main']['temp'])
            descricao = resposta['weather'][0]['description'].capitalize()
            icone = "☀️" if "limpo" in descricao.lower() else "☁️" if "nublado" in descricao.lower() else "🌧️" if "chuva" in descricao.lower() else "⛅"
            return f"{icone} **{temp}°C** - {descricao}"
    except:
        pass
    return None

@st.cache_data
def carregar_gtfs():
    try:
        with gzip.open('trajetos.json.gz', 'rt', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}
trajetos_sp = carregar_gtfs()

# --- INICIALIZAR A MEMÓRIA DO APLICATIVO ---
if 'memoria_origem' not in st.session_state:
    st.session_state.memoria_origem = ""
if 'memoria_destino' not in st.session_state:
    st.session_state.memoria_destino = ""

aba_rota, aba_monitor, aba_ponto = st.tabs(["🗺️ Planejar Rota", "🚌 Monitor Clássico", "🚏 Painel do Ponto"])

# ==========================================
# ABA 1: PLANEJADOR DE ROTAS (VERSÃO CLARA)
# ==========================================
with aba_rota:
    st.subheader("🗺️ Traçar Nova Rota")
    
    # Limpando a memória de busca se necessário
    if 'resultado_busca' not in st.session_state:
        st.session_state['resultado_busca'] = None

    # --- 1. CONFIGURAÇÕES DE VIAGEM ---
    col_m, col_f = st.columns(2)
    with col_m:
        modo_v = st.radio("Como quer ir?", ["🚌 Transporte Público", "🚗 Carro", "🚶 A Pé"], horizontal=True, key="radio_modo_v1")
    with col_f:
        criterio = st.selectbox("Prioridade:", ["⚡ Mais Rápida", "🔄 Menos Baldeações", "🚶 Menos Caminhada"], key="select_ordem_v1")
    
    st.divider()

    # --- 2. DEFINIÇÃO DE ORIGEM E DESTINO ---
    col_origem_config, col_destino_config = st.columns(2)
    
    with col_origem_config:
        st.markdown("**📍 Ponto de Partida**")
        # Criamos uma escolha clara para não haver dúvida
        tipo_origem = st.radio("Definir origem por:", ["⌨️ Digitar Endereço", "🌍 Usar meu GPS"], horizontal=True, key="tipo_origem_v1")
        
        origem_final = None
        
        if tipo_origem == "⌨️ Digitar Endereço":
            origem_txt = st.text_input("Endereço de saída:", placeholder="Ex: Av. Paulista, 1500", key="txt_origem_v1")
            origem_final = origem_txt
        else:
            # Verifica se o GPS na barra lateral foi ativado
            if gps_global and gps_global.get('latitude'):
                origem_final = f"{gps_global['latitude']},{gps_global['longitude']}"
                st.success("✅ GPS capturado com sucesso!")
                st.caption(f"Coordenadas: {origem_final}")
            else:
                st.warning("⚠️ Ative o GPS na barra lateral (menu à esquerda) primeiro!")

    with col_destino_config:
        st.markdown("**🏁 Destino Final**")
        destino_final = st.text_input("Para onde você vai?", placeholder="Ex: Parque Ibirapuera", key="txt_destino_v1")
        st.write("") # Espaçador visual

    # --- 3. DATA E HORÁRIO ---
    st.markdown("### ⏱️ Quando você vai?")
    col_dt, col_hr = st.columns(2)
    with col_dt:
        data_v = st.date_input("Data da viagem:", value=datetime.now(), format="DD/MM/YYYY", key="date_viagem_v1")
    with col_hr:
        hora_v = st.time_input("Horário planejado:", value=datetime.now().time(), key="time_viagem_v1")

    st.divider()

    # --- 4. BOTÃO DE BUSCA E LÓGICA ---
    if st.button("🚀 Buscar Melhores Rotas", type="primary", use_container_width=True, key="btn_busca_v1"):
        if origem_final and destino_final:
            with st.spinner("Analisando mapas e rastreando frotas..."):
                dt_obj = datetime.combine(data_v, hora_v)
                ts = int(dt_obj.timestamp())
                m_google = {"🚌 Transporte Público": "transit", "🚗 Carro": "driving", "🚶 A Pé": "walking"}[modo_v]
                
                # Chamada API Google
                url = f"https://maps.googleapis.com/maps/api/directions/json?origin={origem_final}&destination={destino_final}&mode={m_google}&departure_time={ts}&alternatives=true&language=pt-BR&key={CHAVE_GOOGLE}"
                res = requests.get(url).json()
                
                if res['status'] == 'OK':
                    st.session_state['resultado_busca'] = res['routes']
                else:
                    st.error("O Google não encontrou essa rota. Verifique se o endereço ou o GPS estão corretos.")
        else:
            st.warning("Preencha o destino e defina a origem para continuar.")

    # --- 5. EXIBIÇÃO DOS RESULTADOS (MEMÓRIA PERSISTENTE) ---
    if st.session_state['resultado_busca']:
        rotas_encontradas = st.session_state['resultado_busca']
        
        # Algoritmo de Triagem para os Expanders
        for i, r in enumerate(rotas_encontradas):
            leg = r['legs'][0]
            with st.expander(f"Opção {i+1}: {leg['duration']['text']} ({lg['distance']['text'] if 'lg' in locals() else ''})", expanded=(i==0)):
                c1, c2 = st.columns([4, 6])
                with c1:
                    st.write("**Instruções detalhadas:**")
                    for p in leg['steps']:
                        inst = p['html_instructions'].replace('<b>','**').replace('</b>','**').replace('<div style="font-size:0.9em">',' (').replace('</div>',')')
                        
                        if p['travel_mode'] == "TRANSIT":
                            det = p.get('transit_details', {})
                            n_lin = det.get('line', {}).get('short_name') or det.get('line', {}).get('name') or "???"
                            st.info(f"🚌 **Linha {n_lin}**\n\n{inst}")
                            
                            # RASTREIO DE PREFIXO EM TEMPO REAL
                            try:
                                s_st = requests.Session()
                                s_st.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
                                l_info = s_st.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={n_lin}").json()
                                if l_info:
                                    fr = s_st.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_info[0]['cl']}").json()
                                    if fr and fr['vs']:
                                        prefixos = [v['p'] for v in fr['vs'][:3]]
                                        st.success(f"📡 **Radar:** Veículos {', '.join(prefixos)} na linha.")
                            except: pass
                        else:
                            st.write(f"- {inst}")
                            
                with c2:
                    # Mapa da Rota
                    def decode_v1(p):
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
                    
                    pts = decode_v1(r['overview_polyline']['points'])
                    m_v1 = folium.Map(location=pts[0], zoom_start=13, tiles='CartoDB positron')
                    folium.PolyLine(pts, color="#00A1FF", weight=5).add_to(m_v1)
                    folium.Marker(pts[0], icon=folium.Icon(color='green', icon='play')).add_to(m_v1)
                    folium.Marker(pts[-1], icon=folium.Icon(color='red', icon='stop')).add_to(m_v1)
                    st_folium(m_v1, width=500, height=350, key=f"mapa_final_v1_{i}")

# ==========================================
# ABA 2: MONITOR DE FROTA (CENTRO DE COMANDO)
# ==========================================
with aba_monitor:
    st.subheader("🚌 Monitor de Frota ao Vivo")
    
    # --- 1. CONFIGURAÇÕES E RADAR ---
    col_a, col_t = st.columns([7, 3])
    with col_a:
        auto_v2 = st.checkbox("🔄 Radar Automático (30s)", value=False, key="check_auto_v2_definitivo")
        if auto_v2: 
            st_autorefresh(interval=30000, key="refresh_v2_definitivo")
    
    # --- 2. ENTRADA DE DADOS ---
    c_lin, c_pref = st.columns(2)
    with c_lin:
        lin_id = st.text_input("🔍 Linha (Número):", placeholder="Ex: 8000", key="in_lin_v2_final")
    with c_pref:
        prefixo_alvo = st.text_input("🎯 Destacar Ônibus (Prefixo):", placeholder="Ex: 12345", key="in_pref_v2_final")

    if lin_id:
        # Autenticação e Busca na SPTrans
        s_m = requests.Session()
        s_m.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")
        res_l = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={lin_id}").json()
        
        if res_l:
            opcoes = {f"{l['lt']}-{l['tl']} | {l['tp']} ➔ {l['ts']}": l for l in res_l}
            sel_v2 = st.selectbox("Sentido da Operação:", list(opcoes.keys()), key="sel_lin_v2_final")
            l_sel = opcoes[sel_v2]
            
            # Puxando posições em tempo real
            frota_res = s_m.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={l_sel['cl']}").json()
            vs = frota_res.get('vs', [])
            
            # --- 3. DASHBOARD DE MÉTRICAS ---
            st.divider()
            c_m1, c_m2, c_m3 = st.columns(3)
            c_m1.metric("🚌 Frota na Rua", len(vs))
            c_m2.metric("♿ Acessíveis", sum(1 for v in vs if v.get('a')))
            c_m3.metric("🕒 Relógio SPTrans", frota_res.get('hr', '--:--'))

            # --- 4. MAPA DE MONITORAMENTO ---
            # Define o centro do mapa (frota ou centro de SP)
            centro_mapa = [vs[0]['py'], vs[0]['px']] if vs else [-23.55, -46.63]
            
            # Escolha automática do tema (Dia/Noite)
            h_atual = datetime.now(pytz.timezone('America/Sao_Paulo')).hour
            tema_mapa = 'CartoDB dark_matter' if (h_atual >= 18 or h_atual < 6) else 'CartoDB positron'
            
            m_frota = folium.Map(location=centro_mapa, zoom_start=13, tiles=tema_mapa)
            
            # Marcador do seu GPS (Vindo da Sidebar)
            if gps_global and gps_global.get('latitude'):
                folium.Marker(
                    [gps_global['latitude'], gps_global['longitude']],
                    popup="Você está aqui",
                    icon=folium.Icon(color='green', icon='user', prefix='fa')
                ).add_to(m_frota)

            if vs:
                lats, lons = [], []
                for v in vs:
                    prefixo_atual = str(v['p'])
                    lats.append(v['py']); lons.append(v['px'])
                    
                    # Lógica de cores do monitor
                    if prefixo_alvo and prefixo_alvo in prefixo_atual:
                        cor_icon = 'orange'  # Ônibus que você está procurando
                    else:
                        cor_icon = 'blue' if v.get('a') else 'red'

                    folium.Marker(
                        [v['py'], v['px']],
                        tooltip=f"Prefixo: {prefixo_atual}",
                        popup=f"🚌 <b>Veículo {prefixo_atual}</b><br>Sinal: {v.get('t', 'Real')}",
                        icon=folium.Icon(color=cor_icon, icon='bus', prefix='fa')
                    ).add_to(m_frota)
                
                # Ajusta o zoom automaticamente para abraçar todos os ônibus
                m_frota.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
            
            st_folium(m_frota, width=1000, height=500, key="mapa_v2_final_corrigido")
            
            # --- 5. RAIO-X DA FROTA (VERSÃO BLINDADA CONTRA ERROS) ---
            st.markdown("### 📋 Detalhamento dos Veículos")
            if vs:
                df_raw = pd.DataFrame(vs)
                
                # O reindex impede o KeyError se uma coluna sumir da API
                df_view = df_raw.reindex(columns=['p', 't', 'a'], fill_value="N/D")
                df_view.columns = ['Prefixo', 'Último Sinal', 'Acessível']
                
                # Formatação visual da acessibilidade
                df_view['Acessível'] = df_view['Acessível'].apply(
                    lambda x: "✅ Sim" if x is True else "❌ Não" if x is False else "N/D"
                )
                
                # Se houver busca por prefixo, filtra a tabela também
                if prefixo_alvo:
                    df_view = df_view[df_view['Prefixo'].astype(str).str.contains(prefixo_alvo)]
                
                st.dataframe(df_view, use_container_width=True, hide_index=True)
            else:
                st.info("Aguardando sinal dos veículos para listar a frota.")
        else:
            st.error("Linha não encontrada na base da SPTrans.")

# ==========================================
# ABA 3: PAINEL DO PONTO (VERSÃO PROXIMIDADE)
# ==========================================
import math

with aba_ponto:
    st.subheader("🚏 Painel de Chegada em Tempo Real")
    
    # --- 1. FUNÇÃO AUXILIAR DE DISTÂNCIA ---
    def calcular_distancia(lat1, lon1, lat2, lon2):
        # Fórmula simples para distância em metros
        return math.sqrt((lat1 - lat2)**2 + (lon1 - lon2)**2) * 111320

    # --- 2. BUSCA E LOCALIZAÇÃO ---
    col_busca, col_filtros = st.columns([6, 4])
    
    with col_busca:
        termo_ponto = st.text_input("🔍 Buscar ponto (Rua ou Código):", placeholder="Ex: Av. Paulista ou 2600123", key="in_ponto_v3_ref")
    
    with col_filtros:
        so_acessivel = st.toggle("♿ Apenas Acessíveis", value=False, key="toggle_acess_v3")
        auto_refresh_ponto = st.checkbox("🔄 Atualizar (30s)", value=True, key="check_ponto_refresh")
        if auto_refresh_ponto:
            st_autorefresh(interval=30000, key="refresh_ponto_v3")

    # --- 3. LOGICA DE SELEÇÃO DE PONTO ---
    s_p = requests.Session()
    s_p.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={TOKEN_SPTRANS}")

    ponto_selecionado = None

    # Se o usuário não digitou nada, mas o GPS está ligado, buscamos pontos próximos
    if not termo_ponto and gps_global and gps_global.get('latitude'):
        with st.spinner("Buscando pontos ao seu redor..."):
            lat_u = gps_global['latitude']
            lon_u = gps_global['longitude']
            # Busca pontos em um raio de 500m (API SPTrans)
            pontos_prox = s_p.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Parada/BuscarParadasProximas?lat={lat_u}&lon={lon_u}&raio=500").json()
            
            if pontos_prox:
                st.info(f"📍 Encontramos {len(pontos_prox)} pontos próximos a você.")
                dict_prox = {f"{p['np']} ({p['ed']}) - {int(calcular_distancia(lat_u, lon_u, p['py'], p['px']))}m": p for p in pontos_prox}
                sel_prox = st.selectbox("Escolha um ponto próximo:", list(dict_prox.keys()), key="sel_prox_v3")
                ponto_selecionado = dict_prox[sel_prox]
    
    # Se o usuário digitou algo na busca
    elif termo_ponto:
        pontos_busca = s_p.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Parada/Buscar?termosBusca={termo_ponto}").json()
        if pontos_busca:
            dict_busca = {f"{p['np']} ({p['ed']})": p for p in pontos_busca}
            sel_b = st.selectbox("Selecione o ponto:", list(dict_busca.keys()), key="sel_busca_v3")
            ponto_selecionado = dict_busca[sel_b]

    # --- 4. EXIBIÇÃO DAS PREVISÕES ---
    if ponto_selecionado:
        cp = ponto_selecionado['cp']
        
        # Mostra distância se o GPS estiver on
        if gps_global and gps_global.get('latitude'):
            dist = calcular_distancia(gps_global['latitude'], gps_global['longitude'], ponto_selecionado['py'], ponto_selecionado['px'])
            st.write(f"🚶 Você está a aproximadamente **{int(dist)} metros** deste ponto.")

        with st.spinner("Consultando cronômetro da SPTrans..."):
            previsao = s_p.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Previsao/Parada?codigoParada={cp}").json()
        
        if previsao and 'p' in previsao:
            linhas = previsao['p'].get('l', [])
            
            if not linhas:
                st.warning("Nenhum ônibus vindo para este ponto agora.")
            else:
                for lin in linhas:
                    # Filtro de Acessibilidade
                    veiculos_filtrados = [v for v in lin['vs'] if not so_acessivel or v.get('a')]
                    
                    if veiculos_filtrados:
                        # Pegamos o primeiro ônibus que vai chegar
                        v_prox = veiculos_filtrados[0]
                        tempo = v_prox['t'] # Ex: "12:45" ou "5 min"
                        
                        # Lógica de Cor: Se chegar em menos de 5 min ou estiver "quase lá"
                        # Nota: A API as vezes manda horário, as vezes minutos. Vamos tratar o texto:
                        está_perto = "min" in tempo and int(tempo.replace(" min", "")) <= 5
                        cor_alerta = "inverse" if está_perto else "off"

                        with st.chat_message("bus" if not está_perto else "user"): # Muda o ícone se estiver perto
                            c1, c2, c3 = st.columns([2, 5, 3])
                            with c1:
                                st.markdown(f"### {lin['c']}")
                            with c2:
                                st.write(f"**{lin['lt0']} ➔ {lin['lt1']}**")
                                st.caption(f"Prefixo: {v_prox['p']} {'♿' if v_prox.get('a') else ''}")
                            with c3:
                                if está_perto:
                                    st.error(f"⏱️ {tempo}")
                                    st.caption("Corre que está vindo!")
                                else:
                                    st.subheader(f"⏱️ {tempo}")

                # --- MAPA DO PONTO E ÔNIBUS VINDO ---
                st.divider()
                st.markdown("### 🗺️ Radar do Ponto")
                m_v3 = folium.Map(location=[ponto_selecionado['py'], ponto_selecionado['px']], zoom_start=16, tiles='CartoDB positron')
                
                # Ícone do Ponto
                folium.Marker([ponto_selecionado['py'], ponto_selecionado['px']], 
                              icon=folium.Icon(color='blue', icon='map-pin', prefix='fa'),
                              popup="Ponto Selecionado").add_to(m_v3)
                
                # Ônibus que estão chegando (Laranja)
                for lin in linhas:
                    for v in lin['vs']:
                        folium.Marker([v['py'], v['px']], 
                                      icon=folium.Icon(color='orange', icon='bus', prefix='fa'),
                                      popup=f"Linha {lin['c']} - Chega em {v['t']}").add_to(m_v3)
                
                st_folium(m_v3, width=1000, height=400, key="mapa_ponto_refinado")
        else:
            st.info("Buscando dados de tempo real...")