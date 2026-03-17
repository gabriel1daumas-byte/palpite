import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, time
import pytz

# --- CONFIGURAÇÃO INICIAL E CONEXÃO ---
st.set_page_config(page_title="Bolão da Galera", page_icon="🏆", layout="centered")

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()
fuso_br = pytz.timezone('America/Sao_Paulo')

# --- CONTROLE DE SESSÃO (LOGIN) ---
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.nome_usuario = ""
    st.session_state.email_usuario = ""

# ==========================================
# TELA DE LOGIN (BARREIRA DE ACESSO)
# ==========================================
if not st.session_state.logado:
    st.title("🔒 Acesso ao Bolão")
    st.write("Digite seu e-mail cadastrado para acessar.")
    
    with st.form("form_login"):
        email_digitado = st.text_input("Seu E-mail:")
        submit_login = st.form_submit_button("Entrar")
        
        if submit_login:
            if email_digitado:
                email_limpo = email_digitado.lower().strip()
                resposta = supabase.table("usuarios").select("*").eq("email", email_limpo).execute()
                
                if len(resposta.data) > 0:
                    st.session_state.logado = True
                    st.session_state.nome_usuario = resposta.data[0]['nome']
                    st.session_state.email_usuario = email_limpo
                    st.rerun()
                else:
                    st.error("E-mail não encontrado! Fale com o admin para liberar seu acesso.")
            else:
                st.warning("Por favor, digite um e-mail.")

# ==========================================
# SISTEMA PRINCIPAL (SÓ PARA LOGADOS)
# ==========================================
else:
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("🏆 Bolão da Galera")
        st.write(f"Fala, **{st.session_state.nome_usuario}**! Boa sorte na rodada.")
    with col2:
        if st.button("Sair"):
            st.session_state.logado = False
            st.rerun()
            
    st.divider()

    menu = st.sidebar.selectbox("Navegação", 
                                ["Fazer Palpites", "Ver Palpites da Galera", "Classificação", "⚙️ Admin"])

    # ------------------------------------------
    # 1. FAZER PALPITES
    # ------------------------------------------
    if menu == "Fazer Palpites":
        st.subheader("Deixe seus palpites")
        rodada_atual = st.number_input("Selecione a Rodada", min_value=1, step=1)
        
        jogos = supabase.table("jogos").select("*").eq("rodada", rodada_atual).execute().data
        
        if not jogos:
            st.info("Nenhum jogo cadastrado para essa rodada ainda.")
        else:
            agora = datetime.now(fuso_br)
            
            with st.form("form_palpites"):
                palpites_feitos = {}
                jogos_abertos = 0
                
                for jogo in jogos:
                    st.write(f"**{jogo['time_casa']} x {jogo['time_fora']}**")
                    
                    # Checa o horário de fechamento
                    if jogo.get('horario_fechamento'):
                        fechamento = datetime.fromisoformat(jogo['horario_fechamento'])
                        
                        if agora < fechamento:
                            st.caption(f"⏳ Fecha em: {fechamento.strftime('%d/%m às %H:%M')}")
                            opcoes = [jogo['time_casa'], "Empate", jogo['time_fora']]
                            escolha = st.radio("Vencedor:", opcoes, horizontal=True, key=f"jogo_{jogo['id']}")
                            palpites_feitos[jogo['id']] = escolha
                            jogos_abertos += 1
                        else:
                            st.error(f"🔒 Palpites encerrados (Fechou {fechamento.strftime('%d/%m %H:%M')})")
                    else:
                        # Jogos sem horário cadastrado ficam abertos por padrão
                        opcoes = [jogo['time_casa'], "Empate", jogo['time_fora']]
                        escolha = st.radio("Vencedor:", opcoes, horizontal=True, key=f"jogo_{jogo['id']}")
                        palpites_feitos[jogo['id']] = escolha
                        jogos_abertos += 1
                        
                    st.write("---")
                
                enviar = st.form_submit_button("Salvar Palpites")
                
                if enviar and jogos_abertos > 0:
                    for id_jogo, palpite in palpites_feitos.items():
                        supabase.table("palpites").delete().match({"nome_amigo": st.session_state.nome_usuario, "id_jogo": id_jogo}).execute()
                        supabase.table("palpites").insert({
                            "nome_amigo": st.session_state.nome_usuario,
                            "id_jogo": id_jogo,
                            "palpite": palpite
                        }).execute()
                    st.success("Palpites salvos com sucesso!")

    # ------------------------------------------
    # 2. VER PALPITES
    # ------------------------------------------
    elif menu == "Ver Palpites da Galera":
        st.subheader("Quem apostou no que?")
        rodada = st.number_input("Rodada", min_value=1, step=1)
        
        jogos = supabase.table("jogos").select("*").eq("rodada", rodada).execute().data
        palpites = supabase.table("palpites").select("*").execute().data
        
        if jogos and palpites:
            df_jogos = pd.DataFrame(jogos)
            df_palpites = pd.DataFrame(palpites)
            
            ids_jogos_rodada = df_jogos['id'].tolist()
            df_palpites_rodada = df_palpites[df_palpites['id_jogo'].isin(ids_jogos_rodada)]
            
            if not df_palpites_rodada.empty:
                df_completo = pd.merge(df_palpites_rodada, df_jogos, left_on="id_jogo", right_on="id")
                df_completo["Partida"] = df_completo["time_casa"] + " x " + df_completo["time_fora"]
                
                tabela = df_completo.pivot_table(index="nome_amigo", columns="Partida", values="palpite", aggfunc='first')
                st.dataframe(tabela, use_container_width=True)
            else:
                st.info("Ninguém palpitou nessa rodada ainda.")
        else:
            st.info("Sem dados para exibir.")

    # ------------------------------------------
    # 3. CLASSIFICAÇÃO
    # ------------------------------------------
    elif menu == "Classificação":
        st.subheader("Tabela de Pontos")
        
        jogos = supabase.table("jogos").select("*").execute().data
        palpites = supabase.table("palpites").select("*").execute().data
        usuarios = supabase.table("usuarios").select("nome").execute().data
        
        pontuacao = {u['nome']: 0 for u in usuarios}
        
        for p in palpites:
            amigo = p["nome_amigo"]
            jogo_referencia = next((j for j in jogos if j["id"] == p["id_jogo"]), None)
            
            if jogo_referencia and jogo_referencia["resultado_real"]:
                if p["palpite"] == jogo_referencia["resultado_real"]:
                    if amigo in pontuacao:
                        pontuacao[amigo] += 1
                    
        if pontuacao:
            df_ranking = pd.DataFrame(list(pontuacao.items()), columns=["Nome", "Pontos"])
            df_ranking = df_ranking.sort_values(by="Pontos", ascending=False).reset_index(drop=True)
            df_ranking.index += 1
            st.dataframe(df_ranking, use_container_width=True)

    # ------------------------------------------
    # 4. ADMIN
    # ------------------------------------------
    elif menu == "⚙️ Admin":
        st.warning("Área Restrita")
        senha = st.text_input("Senha Admin", type="password")
        
        if senha == "1234":
            st.subheader("1. Cadastrar Novo Jogo")
            with st.form("novo_jogo"):
                col1, col2, col3 = st.columns([1, 2, 2])
                rod = col1.number_input("Rod", min_value=1, step=1)
                casa = col2.text_input("Time Mandante")
                fora = col3.text_input("Time Visitante")
                
                col4, col5 = st.columns(2)
                data_fechamento = col4.date_input("Data Limite (Fechamento)")
                hora_fechamento = col5.time_input("Hora Limite", value=time(16, 0))
                
                if st.form_submit_button("Cadastrar Partida"):
                    # Combina data e hora e aplica o fuso horário de Brasília
                    dt_fechamento = fuso_br.localize(datetime.combine(data_fechamento, hora_fechamento))
                    
                    supabase.table("jogos").insert({
                        "rodada": rod, 
                        "time_casa": casa, 
                        "time_fora": fora,
                        "horario_fechamento": dt_fechamento.isoformat()
                    }).execute()
                    st.success(f"Jogo adicionado! Fechamento: {dt_fechamento.strftime('%d/%m %H:%M')}")
            
            st.divider()
            
            st.subheader("2. Lançar Resultado Final")
            rod_resultado = st.number_input("Filtrar por Rodada", min_value=1, step=1, key="rod_res")
            jogos_pendentes = supabase.table("jogos").select("*").eq("rodada", rod_resultado).is_("resultado_real", "null").execute().data
            
            if jogos_pendentes:
                for jogo in jogos_pendentes:
                    st.write(f"**{jogo['time_casa']} x {jogo['time_fora']}**")
                    vencedor = st.selectbox("Quem ganhou?", [jogo['time_casa'], "Empate", jogo['time_fora']], key=f"res_{jogo['id']}")
                    if st.button("Salvar Resultado", key=f"btn_{jogo['id']}"):
                        supabase.table("jogos").update({"resultado_real": vencedor}).eq("id", jogo["id"]).execute()
                        st.success("Resultado atualizado! Ranking recalculado.")
                        st.rerun()
            else:
                st.write("Nenhum jogo aguardando resultado nesta rodada.")