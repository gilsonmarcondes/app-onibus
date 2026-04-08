import requests
import streamlit as st
import json
import os
import gzip
import math

@st.cache_resource(show_spinner=False)
def criar_sessao(token):
    """Cria e autentica a sessão com a API da SPTrans."""
    s = requests.Session()
    if token:
        try:
            s.post(f"http://api.olhovivo.sptrans.com.br/v2.1/Login/Autenticar?token={token}", timeout=10)
        except requests.exceptions.Timeout:
            st.warning("⏱️ Timeout ao autenticar na SPTrans. Dados em tempo real podem estar indisponíveis.")
        except requests.exceptions.ConnectionError:
            st.warning("🌐 Não foi possível conectar à API SPTrans. Verifique sua conexão.")
        except Exception as e:
            st.warning(f"Erro ao autenticar na SPTrans: {e}")
    return s

@st.cache_data(show_spinner=False)
def carregar_dados_locais():
    """Carrega as paradas, horários e trajetos dos arquivos JSON."""
    paradas, horarios, trajetos = [], {}, {}
    if os.path.exists("paradas.json"):
        with open("paradas.json", "r", encoding="utf-8") as f: paradas = json.load(f)
    if os.path.exists("horarios.json"):
        with open("horarios.json", "r", encoding="utf-8") as f: horarios = json.load(f)
    if os.path.exists("trajetos.json.gz"):
        with gzip.open("trajetos.json.gz", "rt", encoding="utf-8") as f: trajetos = json.load(f)
    return paradas, horarios, trajetos

def buscar_linha(sessao, termo):
    try:
        return sessao.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Linha/Buscar?termosBusca={termo}", timeout=10).json()
    except Exception as e:
        st.error(f"Erro ao buscar linha na SPTrans: {e}")
        return []

def buscar_posicao_veiculos(sessao, codigo_linha):
    try:
        return sessao.get(f"http://api.olhovivo.sptrans.com.br/v2.1/Posicao/Linha?codigoLinha={codigo_linha}", timeout=10).json()
    except Exception as e:
        st.error(f"Erro ao buscar posição dos veículos: {e}")
        return {}

def calcular_distancia_haversine(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))