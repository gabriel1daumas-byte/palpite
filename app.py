import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, time, timedelta
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

# --- FUNÇÃO PARA CONVERTER O HORÁRIO DO BANCO PARA BRASÍLIA ---
def converter_para_br(data_string):
    if data_string.endswith('Z'):
        data_string = data_string[:-1] + '+00:00'
    return datetime.fromisoformat(data_string).astimezone(fuso_br)

# --- CONTROLE DE SESSÃO ---
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.nome_usuario = ""
    st.session_state.email_usuario = ""
    st.session_state.is_admin = False

# ==========================================
# TELA DE ACESSO (LOGIN / CADASTRO DE SENHA)
# ==========================================
if not st.session_state.logado:
    st.title("🔒 Acesso ao Bolão")
    st.write("Identifique-se para acessar os palpites.")
    
    email_digitado = st.text_input("Qual o seu e-mail?")
    
    if email_digitado:
        email_limpo = email_digitado.lower().strip()
        resposta = supabase.table("usuarios").select("*").eq("email", email_limpo).execute()
        
        if len(resposta.data) > 0:
            usuario = resposta.data[0]
            
            if usuario.get("senha") is None or usuario.get("senha") == "":
                st.info(f"Olá, {usuario['nome']}! Este é seu primeiro acesso. Crie uma senha para continuar.")
                nova_senha = st.text_input("Crie sua senha:", type="password")
                
                if st.button("Salvar Senha e Entrar"):
                    if nova_senha:
                        supabase.table("usuarios").update({"senha": nova_senha}).eq("email", email_limpo).execute()
                        st.success("Senha cadastrada!")
                        st.session_state.logado = True
                        st.session_state.nome_usuario = usuario['nome']
                        st.session_state.email_usuario = email_limpo
                        st.session_state.is_admin = usuario.get('is_admin', False)
                        st.rerun()
                    else:
                        st.warning("A senha não pode ser vazia.")
            else:
                senha_digitada = st.text_input("Sua Senha:", type="password")
                
                if st.button("Entrar"):
                    if senha_digitada == usuario["senha"]:
                        st.session_state.logado = True
                        st.session_state.nome_usuario = usuario['nome']
                        st.session_state.email_usuario = email_limpo
                        st.session_state.is_admin = usuario.get('is_admin', False)
                        st.rerun()
                    else:
                        st.error("Senha incorreta!")
        else:
            st.error("E-mail não está na lista de convidados! Fale com o admin.")

# ==========================================
# SISTEMA PRINCIPAL (SÓ PARA LOGADOS)
# ==========================================
else:
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("🏆 Bolão da Galera")
        st.write(f"Fala, **{st.session_state.nome_usuario}**!")
    with col2:
        if st.button("Sair"):
            st.session_state.logado = False
            st.session_state.is_admin = False
            st.rerun()
            
    st.divider()

    opcoes_menu = ["Fazer Palpites", "Meus Palpites", "Ver Palpites da Galera", "Classificação"]
    if st.session_state.is_admin:
        opcoes_menu.append("⚙️ Admin")
        
    menu = st.sidebar.selectbox("Navegação", opcoes_menu)

    # ------------------------------------------
    # 1. FAZER PALPITES (AGORA COM TRAVA DEFINITIVA)
    # ------------------------------------------
    if menu == "Fazer Palpites":
        st.subheader("Deixe seus palpites")
        rodada_atual = st.number_input("Selecione a Rodada", min_value=1, step=1)
        
        jogos = supabase.table("jogos").select("*").eq("rodada", rodada_atual).execute().data
        
        if not jogos:
            st.info("Nenhum jogo cadastrado para essa rodada ainda.")
        else:
            agora = datetime.now(fuso_br)
            
            # Puxa do banco todos os palpites que esse usuário JÁ FEZ nessa rodada
            ids_jogos_rodada = [j['id'] for j in jogos]
            palpites_existentes = supabase.table("palpites").select("id_jogo, palpite").eq("nome_amigo", st.session_state.nome_usuario).in_("id_jogo", ids_jogos_rodada).execute().data
            
            # Cria um dicionário fácil para checar se ele já apostou no jogo X
            mapa_ja_palpitou = {p['id_jogo']: p['palpite'] for p in palpites_existentes}
            
            with st.form("form_palpites"):
                palpites_feitos = {}
                jogos_abertos = 0
                
                for jogo in jogos:
                    st.write(f"**{jogo['time_casa']} x {jogo['time_fora']}**")
                    
                    # 1ª CHECAGEM: Ele já deu o palpite para esse jogo antes?
                    if jogo['id'] in mapa_ja_palpitou:
                        st.success(f"✅ Palpite travado: **{mapa_ja_palpitou[jogo['id']]}**")
                    
                    # Se não palpitou ainda, vai para a 2ª CHECAGEM: O jogo ainda está aberto?
                    else:
                        if jogo.get('horario_fechamento'):
                            fechamento = converter_para_br(jogo['horario_fechamento'])
                            
                            if agora < fechamento:
                                st.caption(f"⏳ Fecha em: {fechamento.strftime('%d/%m às %H:%M')}")
                                opcoes = [jogo['time_casa'], "Empate", jogo['time_fora']]
                                escolha = st.radio("Vencedor:", opcoes, horizontal=True, key=f"jogo_{jogo['id']}")
                                palpites_feitos[jogo['id']] = escolha
                                jogos_abertos += 1
                            else:
                                st.error(f"🔒 Palpites encerrados (Fechou {fechamento.strftime('%d/%m %H:%M')})")
                        else:
                            opcoes = [jogo['time_casa'], "Empate", jogo['time_fora']]
                            escolha = st.radio("Vencedor:", opcoes, horizontal=True, key=f"jogo_{jogo['id']}")
                            palpites_feitos[jogo['id']] = escolha
                            jogos_abertos += 1
                        
                    st.write("---")
                
                # Só mostra o botão se tiver algum jogo novo para preencher
                if jogos_abertos > 0:
                    enviar = st.form_submit_button("Salvar Novos Palpites")
                    
                    if enviar:
                        for id_jogo, palpite in palpites_feitos.items():
                            # Faz APENAS o insert, pois o usuário não consegue mais alterar opções enviadas
                            supabase.table("palpites").insert({
                                "nome_amigo": st.session_state.nome_usuario,
                                "id_jogo": id_jogo,
                                "palpite": palpite
                            }).execute()
                        st.success("Palpites salvos e trancados com sucesso!")
                        st.rerun() # Recarrega a página para atualizar o status para "Travado"
                else:
                    st.form_submit_button("Todos os palpites foram feitos ou estão fechados", disabled=True)

    # ------------------------------------------
    # 2. MEUS PALPITES 
    # ------------------------------------------
    elif menu == "Meus Palpites":
        st.subheader("Meus Palpites")
        
        meus_palpites = supabase.table("palpites").select("*").eq("nome_amigo", st.session_state.nome_usuario).execute().data
        jogos = supabase.table("jogos").select("*").execute().data
        
        if meus_palpites and jogos:
            df_p = pd.DataFrame(meus_palpites)
            df_j = pd.DataFrame(jogos)
            
            df_completo = pd.merge(df_p, df_j, left_on="id_jogo", right_on="id")
            df_completo["Partida"] = df_completo["time_casa"] + " x " + df_completo["time_fora"]
            df_completo["Resultado Real"] = df_completo["resultado_real"].fillna("Aguardando...")
            
            df_view = df_completo[["rodada", "Partida", "palpite", "Resultado Real"]].rename(
                columns={"rodada": "Rodada", "palpite": "Meu Palpite"}
            ).sort_values("Rodada", ascending=False)
            
            st.dataframe(df_view, hide_index=True, use_container_width=True)
        else:
            st.info("Você ainda não fez nenhum palpite.")

    # ------------------------------------------
    # 3. VER PALPITES DA GALERA 
    # ------------------------------------------
    elif menu == "Ver Palpites da Galera":
        st.subheader("Quem apostou no que?")
        rodada = st.number_input("Rodada", min_value=1, step=1)
        
        jogos = supabase.table("jogos").select("*").eq("rodada", rodada).execute().data
        palpites = supabase.table("palpites").select("*").execute().data
        agora = datetime.now(fuso_br)
        
        if jogos and palpites:
            df_jogos = pd.DataFrame(jogos)
            df_palpites = pd.DataFrame(palpites)
            
            map_fechamento = {j['id']: converter_para_br(j['horario_fechamento']) for j in jogos if j.get('horario_fechamento')}
            
            ids_jogos_rodada = df_jogos['id'].tolist()
            df_palpites_rodada = df_palpites[df_palpites['id_jogo'].isin(ids_jogos_rodada)]
            
            if not df_palpites_rodada.empty:
                df_completo = pd.merge(df_palpites_rodada, df_jogos, left_on="id_jogo", right_on="id")
                df_completo["Partida"] = df_completo["time_casa"] + " x " + df_completo["time_fora"]
                
                def aplicar_mascara(row):
                    fechamento = map_fechamento.get(row['id_jogo'])
                    if fechamento and agora < fechamento:
                        return "🔒 Oculto"
                    return row['palpite']
                
                df_completo['palpite_visivel'] = df_completo.apply(aplicar_mascara, axis=1)
                
                tabela = df_completo.pivot_table(index="nome_amigo", columns="Partida", values="palpite_visivel", aggfunc='first')
                st.dataframe(tabela, use_container_width=True)
            else:
                st.info("Ninguém palpitou nessa rodada ainda.")
        else:
            st.info("Sem dados para exibir.")

    # ------------------------------------------
    # 4. CLASSIFICAÇÃO
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
    # 5. ADMIN
    # ------------------------------------------
    elif menu == "⚙️ Admin":
        st.subheader("1. Cadastrar Novo Jogo")
        with st.form("novo_jogo"):
            col1, col2, col3 = st.columns([1, 2, 2])
            rod = col1.number_input("Rod", min_value=1, step=1)
            casa = col2.text_input("Time Mandante")
            fora = col3.text_input("Time Visitante")
            
            col4, col5 = st.columns(2)
            data_jogo = col4.date_input("Data do Jogo")
            hora_jogo = col5.time_input("Hora do Jogo", value=time(16, 0)) 
            
            if st.form_submit_button("Cadastrar Partida"):
                dt_jogo = fuso_br.localize(datetime.combine(data_jogo, hora_jogo))
                dt_fechamento = dt_jogo - timedelta(hours=1, minutes=59)
                
                supabase.table("jogos").insert({
                    "rodada": rod, 
                    "time_casa": casa, 
                    "time_fora": fora,
                    "horario_fechamento": dt_fechamento.isoformat()
                }).execute()
                
                st.success(f"Jogo adicionado! Limite para palpites ficou para: {dt_fechamento.strftime('%d/%m %H:%M')}")
        
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