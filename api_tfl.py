import requests
import pandas as pd
import streamlit as st

def buscar_chegadas_tfl(linha):
    """Consulta a API da TfL e retorna um DataFrame formatado."""
    if not linha:
        return None
        
    try:
        res_tfl = requests.get(f"https://api.tfl.gov.uk/line/{linha}/arrivals", timeout=10).json()
        
        if isinstance(res_tfl, list) and res_tfl:
            df = pd.DataFrame([{
                "Destino": a['destinationName'], 
                "Minutos": a['timeToStation'] // 60,
                "Localização": a['stationName']
            } for a in res_tfl]).sort_values("Minutos")
            return df
            
        elif isinstance(res_tfl, dict) and res_tfl.get('type') == 'Error':
            st.error(f"TfL API: {res_tfl.get('message', 'Erro desconhecido')}")
            
        else:
            st.warning("Linha não encontrada em Londres.")
            
    except requests.exceptions.Timeout:
        st.error("⏱️ Timeout ao consultar a TfL. Tente novamente.")
    except requests.exceptions.ConnectionError:
        st.error("🌐 Sem conexão com a TfL API.")
    except Exception as e:
        st.error(f"Erro inesperado ao consultar TfL: {e}")
        
    return None