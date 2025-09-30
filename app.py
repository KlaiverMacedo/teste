import os
from flask import Flask, request, jsonify
import mysql.connector
from mysql.connector import Error
from flask_cors import CORS

# --- Configurações do seu banco de dados (Lendo Variáveis de Ambiente) ---
# O código lê as variáveis que você configurou no Railway (DB_HOST, DB_USER, etc.)
DB_CONFIG = {
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
    'host': os.environ.get('DB_HOST'),
    'database': os.environ.get('DB_DATABASE'),
    # Converte a porta para inteiro e usa a porta 3306 como fallback seguro
    'port': int(os.environ.get('DB_PORT', 3306)),
    # Adiciona um timeout maior, útil em ambientes de nuvem
    'connection_timeout': 30 
}

app = Flask(__name__)
# Permite que o frontend (Netlify) acesse esta API
CORS(app) 

# --- Função de Conexão com o Banco de Dados ---
def get_db_connection():
    """Tenta estabelecer a conexão com o MySQL usando variáveis de ambiente."""
    try:
        # Verifica se todas as credenciais essenciais estão presentes
        if not all(DB_CONFIG.get(key) for key in ['user', 'password', 'host', 'database']):
            print("ERRO DE CONFIG: Variáveis de ambiente do banco de dados estão faltando ou incompletas.")
            return None
            
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        # Este erro deve aparecer nos Logs do Railway se a conexão falhar
        print(f"ERRO CRÍTICO DE CONEXÃO AO MySQL: {e}")
        return None

# --- ROTAS DE TESTE E SAÚDE ---

@app.route('/', methods=['GET'])
def health_check():
    """Retorna um JSON simples para confirmar que o servidor Flask está rodando."""
    # Tenta fazer uma conexão simples para verificar a saúde do banco de dados também
    conn = get_db_connection()
    if conn:
        conn.close()
        return jsonify({'status': 'ok', 'servico': 'API de Vouchers (Railway)'}), 200
    else:
        return jsonify({'status': 'erro_db', 'servico': 'API de Vouchers (Railway)'}), 500


# --- ROTAS DA API DE VOUCHERS ---

@app.route('/evento', methods=['POST'])
def cadastrar_evento():
    """Cadastra um novo evento no banco de dados."""
    conn = get_db_connection()
    if conn is None: return jsonify({'erro': 'Falha na conexão com o banco de dados'}), 500
    cursor = conn.cursor()
    try:
        data = request.json
        sql = "INSERT INTO eventos (nome, data_evento, data_validade) VALUES (%s, %s, DATE_ADD(%s, INTERVAL 30 DAY))"
        cursor.execute(sql, (data['nome'], data['data'], data['data']))
        conn.commit()
        return jsonify({'sucesso': 'Evento cadastrado', 'id': cursor.lastrowid}), 201
    except Error as e:
        print(f"Erro ao cadastrar evento: {e}")
        return jsonify({'erro': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/vouchers/gerar', methods=['POST'])
def gerar_vouchers_endpoint():
    """Gera uma quantidade específica de vouchers para um evento (chama SP GerarVouchers)."""
    conn = get_db_connection()
    if conn is None: return jsonify({'erro': 'Falha na conexão com o banco de dados'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        data = request.json
        evento_id = data['evento_id']
        quantidade = data['quantidade']
        
        # Chama a Stored Procedure 'GerarVouchers'
        cursor.callproc('GerarVouchers', [evento_id, quantidade])
        conn.commit()
        
        # Busca os vouchers recém-criados para retorno
        sql_query = """
        SELECT
            v.id,
            v.codigo,
            e.nome AS nome_evento,
            DATE_FORMAT(e.data_evento, '%%d/%%m/%%Y') AS data_formatada
        FROM vouchers v
        INNER JOIN eventos e ON v.evento_id = e.id
        WHERE v.evento_id = %s
        ORDER BY v.criado_em DESC
        LIMIT %s
        """
        cursor.execute(sql_query, (evento_id, quantidade))
        vouchers_gerados = cursor.fetchall()
        
        return jsonify({'sucesso': f'{quantidade} vouchers gerados com sucesso.', 'vouchers': vouchers_gerados}), 200
    except Error as e:
        print(f"Erro ao gerar vouchers: {e}")
        return jsonify({'erro': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/relatorios', methods=['GET'])
def relatorio_eventos():
    """Retorna um relatório consolidado (chama SP RelatorioEventos)."""
    conn = get_db_connection()
    if conn is None: return jsonify({'erro': 'Falha na conexão com o banco de dados'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        # Chama a Stored Procedure 'RelatorioEventos'
        cursor.callproc('RelatorioEventos')
        relatorio = []
        for result in cursor.stored_results():
            relatorio = result.fetchall()
        return jsonify(relatorio), 200
    except Error as e:
        print(f"Erro ao gerar relatório: {e}")
        return jsonify({'erro': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/eventos', methods=['GET'])
def listar_eventos():
    """Lista todos os eventos cadastrados."""
    conn = get_db_connection()
    if conn is None: return jsonify({'erro': 'Falha na conexão com o banco de dados'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, nome FROM eventos ORDER BY id DESC")
        eventos = cursor.fetchall()
        return jsonify(eventos), 200
    except Error as e:
        print(f"Erro ao listar eventos: {e}")
        return jsonify({'erro': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/vouchers/<int:evento_id>', methods=['GET'])
def acessar_vouchers(evento_id):
    """Retorna todos os vouchers de um evento específico."""
    conn = get_db_connection()
    if conn is None: return jsonify({'erro': 'Falha na conexão com o banco de dados'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        sql_query = """
        SELECT
            v.id,
            v.codigo,
            e.nome AS nome_evento,
            DATE_FORMAT(e.data_evento, '%%d/%%m/%%Y') AS data_formatada
        FROM vouchers v
        INNER JOIN eventos e ON v.evento_id = e.id
        WHERE v.evento_id = %s
        ORDER BY v.criado_em DESC
        """
        cursor.execute(sql_query, (evento_id,))
        vouchers_existentes = cursor.fetchall()
        
        if not vouchers_existentes:
            return jsonify({'erro': 'Nenhum voucher encontrado para este evento'}), 404
            
        return jsonify({'sucesso': 'Vouchers encontrados.', 'vouchers': vouchers_existentes}), 200
    except Error as e:
        print(f"Erro ao acessar vouchers: {e}")
        return jsonify({'erro': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/voucher/validar', methods=['POST'])
def validar_voucher():
    """Valida um voucher usando a Stored Procedure ValidarVoucher."""
    codigo = request.json.get('codigo')
    if not codigo:
        return jsonify({'erro': 'Código do voucher não fornecido'}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({'erro': 'Falha na conexão com o banco de dados'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        # Chama a Stored Procedure 'ValidarVoucher'
        cursor.callproc('ValidarVoucher', [codigo])
        result = None
        for r in cursor.stored_results():
            result = r.fetchone()
        
        # A SP retorna um dicionário com 'status' e 'evento_nome'
        if result:
            return jsonify(result)
        else:
            # Não deve acontecer, mas é uma segurança
            return jsonify({'status': 'erro_desconhecido', 'evento_nome': None}), 500
            
    except Error as e:
        print(f"Erro ao validar voucher: {e}")
        return jsonify({'erro': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

if __name__ == '__main__':
    # Define a porta que o Railway espera, ou 5000 se rodando localmente
    port = int(os.environ.get('PORT', 5000))
    # Para rodar localmente sem gunicorn
    if 'PORT' not in os.environ: 
        app.run(debug=True, host='0.0.0.0', port=port)
