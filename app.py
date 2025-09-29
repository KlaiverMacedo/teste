from flask import Flask, request, jsonify
import mysql.connector
from mysql.connector import Error
from flask_cors import CORS

# --- Configurações do seu banco de dados (Ajuste para produção!) ---
# ESTE É O BLOCO QUE CONTÉM AS CREDENCIAIS E A LÓGICA DO BANCO
DB_CONFIG = {
    'user': 'root',
    'password': '132318', # Senha do MySQL
    'host': '127.0.0.1',
    'database': 'voucher', # Nome do banco de dados
    'port': 3306 
}

app = Flask(__name__)
# Permite que o frontend (que rodará em outra porta/domínio) acesse esta API
CORS(app) 

# Variável de ambiente (ajuste conforme o ambiente de produção)
API_BASE_URL = "http://127.0.0.1:5000"

# --- Função de Conexão com o Banco de Dados ---
def get_db_connection():
    """Tenta estabelecer a conexão com o MySQL."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Erro ao conectar ao MySQL: {e}")
        return None

# --- Rotas da API ---

@app.route('/evento', methods=['POST'])
def cadastrar_evento():
    """Cadastra um novo evento no banco de dados."""
    conn = get_db_connection()
    if conn is None: return jsonify({'erro': 'Falha na conexão com o banco de dados'}), 500
    cursor = conn.cursor()
    try:
        data = request.json
        # A data_validade é configurada para 30 dias após a data do evento (como no seu código original)
        sql = "INSERT INTO eventos (nome, data_evento, data_validade) VALUES (%s, %s, DATE_ADD(%s, INTERVAL 30 DAY))"
        cursor.execute(sql, (data['nome'], data['data'], data['data']))
        conn.commit()
        return jsonify({'sucesso': 'Evento cadastrado', 'id': cursor.lastrowid}), 201
    except Error as e:
        return jsonify({'erro': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/vouchers/gerar', methods=['POST'])
def gerar_vouchers_endpoint():
    """Gera uma quantidade específica de vouchers para um evento."""
    conn = get_db_connection()
    if conn is None: return jsonify({'erro': 'Falha na conexão com o banco de dados'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        data = request.json
        evento_id = data['evento_id']
        quantidade = data['quantidade']
        
        # Chama a Stored Procedure 'GerarVouchers' no MySQL
        cursor.callproc('GerarVouchers', [evento_id, quantidade])
        conn.commit()
        
        # Busca os vouchers recém-criados para retorno
        sql_query = """
        SELECT
            v.id,
            v.codigo,
            e.nome AS nome_evento,
            DATE_FORMAT(e.data_evento, '%d/%m/%Y') AS data_formatada
        FROM vouchers v
        INNER JOIN eventos e ON v.evento_id = e.id
        WHERE v.evento_id = %s
        ORDER BY v.criado_em DESC
        LIMIT %s
        """
        # O limite é aplicado à ordem inversa para pegar os últimos gerados
        cursor.execute(sql_query, (evento_id, quantidade))
        vouchers_gerados = cursor.fetchall()
        
        return jsonify({'sucesso': f'{quantidade} vouchers gerados com sucesso.', 'vouchers': vouchers_gerados}), 200
    except Error as e:
        return jsonify({'erro': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/relatorios', methods=['GET'])
def relatorio_eventos():
    """Retorna um relatório consolidado de todos os eventos."""
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
        return jsonify({'erro': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/eventos', methods=['GET'])
def listar_eventos():
    """Lista todos os eventos cadastrados para uso em dropdowns."""
    conn = get_db_connection()
    if conn is None: return jsonify({'erro': 'Falha na conexão com o banco de dados'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, nome FROM eventos ORDER BY id DESC")
        eventos = cursor.fetchall()
        return jsonify(eventos), 200
    except Error as e:
        return jsonify({'erro': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/vouchers/<int:evento_id>', methods=['GET'])
def acessar_vouchers(evento_id):
    """Retorna todos os vouchers de um evento específico para impressão."""
    conn = get_db_connection()
    if conn is None: return jsonify({'erro': 'Falha na conexão com o banco de dados'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        sql_query = """
        SELECT
            v.id,
            v.codigo,
            e.nome AS nome_evento,
            DATE_FORMAT(e.data_evento, '%d/%m/%Y') AS data_formatada
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
        return jsonify({'erro': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/voucher/validar', methods=['POST'])
def validar_voucher():
    """Valida um voucher usando o código e registra o uso se for válido."""
    codigo = request.json.get('codigo')
    if not codigo:
        return jsonify({'erro': 'Código do voucher não fornecido'}), 400

    conn = get_db_connection()
    if conn is None:
        return jsonify({'erro': 'Falha na conexão com o banco de dados'}), 500
    cursor = conn.cursor(dictionary=True)
    try:
        # Chama a Stored Procedure 'ValidarVoucher'
        # O resultado da SP deve ser o status do voucher (sucesso, ja_utilizado, expirado, etc.)
        cursor.callproc('ValidarVoucher', [codigo])
        conn.commit() 
        
        result = None
        for r in cursor.stored_results():
            result = r.fetchone() 
            
        if result:
            # Retorna o resultado da SP (ex: {'status': 'sucesso', 'evento_nome': 'Nome do Evento'})
            return jsonify(result), 200
        else:
            # Caso a SP não retorne resultado (voucher não existe)
            return jsonify({'status': 'voucher_nao_encontrado', 'evento_nome': None}), 200
            
    except Error as e:
        # Em caso de erro do SQL
        return jsonify({'erro': str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

if __name__ == '__main__':
    # Roda a aplicação Flask na porta 5000, conforme esperado pelo frontend
    app.run(debug=True, host='127.0.0.1', port=5000)
