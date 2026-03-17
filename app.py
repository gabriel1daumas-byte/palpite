import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timedelta
import pytz

# Configuração da página
st.set_page_config(page_title="Bolão 2026", page_icon="⚽", layout="wide")

# Conexão com o Supabase
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()
fuso_br = pytz.timezone('America/Sao_Paulo')

# ---------------------------------------------------------
# TELA DE LOGIN
# ---------------------------------------------------------
if 'usuario_logado' not in st.session_state:
    st.title("⚽ Bolão Brasileirão 2026")
    st.write("Digite seu e-mail para acessar.")
    
    email_input = st.text_input("E-mail")
    senha_input = st.text_input("Senha", type="password")
    
    if st.button("Entrar"):
        # Busca o usuário no banco
        res = supabase.table("usuarios").select("*").eq("email", email_input).execute()
        
        if len(res.data) > 0:
            user_data = res.data[0]
            
            # Se o usuário ainda não tem senha, cria a senha agora
            if not user_data.get('senha'):
                if senha_input:
                    supabase.table("usuarios").update({"senha": senha_input}).eq("email", email_input).execute()
                    st.session_state['usuario_logado'] = user_data['nome']
                    st.session_state['is_admin'] = user_data.get('is_admin', False)
                    st.success("Senha criada com sucesso! Entrando...")
                    st.rerun()
                else:
                    st.warning("Primeiro acesso: Digite uma senha para registrar sua conta.")
            # Se já tem senha, verifica se está correta
            elif user_data.get('senha') == senha_input:
                st.session_state['usuario_logado'] = user_data['nome']
                st.session_state['is_admin'] = user_data.get('is_admin', False)
                st.rerun()
            else:
                st.error("Senha incorreta.")
        else:
            st.error("E-mail não encontrado.")
            
    st.stop() # Para a execução aqui se não estiver logado

# ---------------------------------------------------------
# SISTEMA PRINCIPAL (Logado)
# ---------------------------------------------------------
st.sidebar.title(f"Olá, {st.session_state['usuario_logado']}")
if st.sidebar.button("Sair"):
    st.session_state.clear()
    st.rerun()

# Define as abas com base no tipo de usuário
if st.session_state.get('is_admin'):
    abas = st.tabs(["⚽ Palpites", "🏆 Classificação", "⚙️ Admin"])
else:
    abas = st.tabs(["⚽ Palpites", "🏆 Classificação"])

# ---------------------------------------------------------
# ABA 1: PALPITES
# ---------------------------------------------------------
with abas[0]:
    st.header("Faça seus Palpites")
    
    # Busca jogos que ainda não fecharam e não tem resultado oficial
    agora = datetime.now(fuso_br).isoformat()
    res_jogos = supabase.table("jogos").select("*").filter("horario_fechamento", "gt", agora).is_("resultado_real", "null").order("horario_fechamento").execute()
    
    if not res_jogos.data:
        st.info("Nenhum jogo aberto para palpites no momento.")
    else:
        # Busca os palpites já feitos por esse usuário para preencher os campos
        res_meus_palpites = supabase.table("palpites").select("*").eq("nome_amigo", st.session_state['usuario_logado']).execute()
        meus_palpites_dict = {p['id_jogo']: p['palpite'] for p in res_meus_palpites.data}
        
        with st.form("form_palpites"):
            palpites_novos = {}
            for jogo in res_jogos.data:
                st.write(f"**Rodada {jogo['rodada']}** - Fechamento: {pd.to_datetime(jogo['horario_fechamento']).strftime('%d/%m/%Y %H:%M')}")
                
                opcoes = [jogo['time_casa'], 'Empate', jogo['time_fora']]
                palpite_atual = meus_palpites_dict.get(jogo['id'], 'Empate') # Padrão é empate
                
                try:
                    index_padrao = opcoes.index(palpite_atual)
                except ValueError:
                    index_padrao = 1
                
                escolha = st.radio(
                    f"{jogo['time_casa']} x {jogo['time_fora']}", 
                    opcoes, 
                    index=index_padrao,
                    horizontal=True,
                    key=f"jogo_{jogo['id']}"
                )
                palpites_novos[jogo['id']] = escolha
                st.divider()
                
            submit = st.form_submit_button("Salvar Palpites")
            
            if submit:
                for id_jogo, palpite in palpites_novos.items():
                    # Insere ou atualiza (Upsert)
                    dados = {
                        "nome_amigo": st.session_state['usuario_logado'],
                        "id_jogo": id_jogo,
                        "palpite": palpite
                    }
                    # Executa o upsert via Supabase (requer que nome_amigo e id_jogo sejam chaves únicas)
                    # Caso dê erro, mude para um delete + insert
                    supabase.table("palpites").upsert(dados, on_conflict="nome_amigo, id_jogo").execute()
                    
                st.success("Palpites salvos com sucesso!")

# ---------------------------------------------------------
# ABA 2: CLASSIFICAÇÃO E TOTAL POR RODADA
# ---------------------------------------------------------
with abas[1]:
    st.header("🏆 Classificação Geral")
    
    # Busca palpites e jogos com resultado
    res_todos_palpites = supabase.table("palpites").select("*").execute()
    res_jogos_encerrados = supabase.table("jogos").select("id, rodada, resultado_real").not_.is_("resultado_real", "null").execute()
    
    if not res_jogos_encerrados.data:
        st.info("Ainda não há resultados finais lançados.")
    elif not res_todos_palpites.data:
         st.info("Nenhum palpite registrado ainda.")
    else:
        df_palpites = pd.DataFrame(res_todos_palpites.data)
        df_jogos = pd.DataFrame(res_jogos_encerrados.data)
        
        # Junta as duas tabelas
        df_completo = pd.merge(df_palpites, df_jogos, left_on="id_jogo", right_on="id")
        
        # Limpeza mágica para evitar divergências de acentos/espaços (strip + lower)
        df_completo['palpite_clean'] = df_completo['palpite'].astype(str).str.strip().str.lower()
        df_completo['resultado_clean'] = df_completo['resultado_real'].astype(str).str.strip().str.lower()
        
        # Calcula pontos (1 ponto por acerto)
        df_completo['pontos'] = (df_completo['palpite_clean'] == df_completo['resultado_clean']).astype(int)
        
        # TABELA 1: CLASSIFICAÇÃO GERAL
        df_geral = df_completo.groupby('nome_amigo')['pontos'].sum().reset_index()
        df_geral = df_geral.sort_values(by='pontos', ascending=False).reset_index(drop=True)
        df_geral.index += 1
        df_geral.columns = ['Participante', 'Pontuação Total']
        
        st.dataframe(df_geral, use_container_width=True)
        
        # TABELA 2: TOTAL POR RODADA (Estilo Planilha)
        st.divider()
        st.subheader("📊 Total de Pontos por Rodada")
        
        # Agrupa por amigo e rodada
        df_agrupado = df_completo.groupby(['nome_amigo', 'rodada'])['pontos'].sum().reset_index()
        
        # Cria a tabela dinâmica (Pivot)
        df_pivot = df_agrupado.pivot(index='nome_amigo', columns='rodada', values='pontos').fillna(0).astype(int)
        
        # Formata o nome das colunas
        df_pivot.columns = [f"Rodada {col}" for col in df_pivot.columns]
        
        # Adiciona o Total Geral no final da linha
        df_pivot['Total Geral'] = df_pivot.sum(axis=1)
        
        # Ordena a tabela pela pontuação total
        df_pivot = df_pivot.sort_values(by='Total Geral', ascending=False)
        
        # Mostra na tela
        st.dataframe(df_pivot, use_container_width=True)

# ---------------------------------------------------------
# ABA 3: ADMIN (Só aparece para administradores)
# ---------------------------------------------------------
if st.session_state.get('is_admin'):
    with abas[2]:
        st.header("Painel do Administrador")
        
        # --- ATUALIZAR RESULTADOS REAIS ---
        st.subheader("Lançar Resultados")
        jogos_sem_resultado = supabase.table("jogos").select("*").is_("resultado_real", "null").order("horario_fechamento").execute()
        
        if jogos_sem_resultado.data:
            with st.form("form_resultados"):
                resultados_novos = {}
                for jogo in jogos_sem_resultado.data:
                    opcoes_res = [jogo['time_casa'], 'Empate', jogo['time_fora'], 'Ainda não jogou']
                    escolha_res = st.selectbox(
                        f"Rodada {jogo['rodada']} | {jogo['time_casa']} x {jogo['time_fora']}",
                        opcoes_res,
                        index=3,
                        key=f"res_{jogo['id']}"
                    )
                    if escolha_res != 'Ainda não jogou':
                        resultados_novos[jogo['id']] = escolha_res
                
                if st.form_submit_button("Salvar Resultados"):
                    for id_j, res in resultados_novos.items():
                        supabase.table("jogos").update({"resultado_real": res}).eq("id", id_j).execute()
                    st.success("Resultados atualizados! A classificação foi recalculada.")
                    st.rerun()
        else:
            st.info("Todos os jogos cadastrados já possuem resultado final.")
            
        st.divider()
        
        # --- CADASTRAR NOVO JOGO MANUALMENTE ---
        st.subheader("Cadastrar Jogo Manual")
        with st.form("form_novo_jogo"):
            col1, col2, col3 = st.columns(3)
            with col1:
                rodada = st.number_input("Rodada", min_value=1, step=1)
            with col2:
                time_casa = st.text_input("Time da Casa")
            with col3:
                time_fora = st.text_input("Time de Fora")
                
            data_jogo = st.date_input("Data do Jogo")
            hora_jogo = st.time_input("Horário Oficial do Jogo")
            
            if st.form_submit_button("Cadastrar Jogo"):
                if time_casa and time_fora:
                    # Calcula o horário de fechamento (-1h59m)
                    dt_jogo = datetime.combine(data_jogo, hora_jogo)
                    dt_jogo_local = fuso_br.localize(dt_jogo)
                    dt_fechamento = dt_jogo_local - timedelta(hours=1, minutes=59)
                    
                    supabase.table("jogos").insert({
                        "rodada": rodada,
                        "time_casa": time_casa,
                        "time_fora": time_fora,
                        "horario_fechamento": dt_fechamento.isoformat()
                    }).execute()
                    st.success("Jogo cadastrado com sucesso!")
                else:
                    st.error("Preencha o nome dos times.")