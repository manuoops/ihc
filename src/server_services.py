import argparse
import json
import os
import re
import sqlite3
import time
import sys
from contextlib import asynccontextmanager, closing
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import dspy
from fastapi import FastAPI, HTTPException, Query

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DB_PATH = BASE_DIR / "lojas.db"
MODEL_ARTIFACT = BASE_DIR / "sql_generator_optimized.json"
SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS produtos (
    produto TEXT NOT NULL,
    departamento TEXT NOT NULL,
    id INTEGER NOT NULL,
    data_fabri DATE,
    data_venc DATE,
    custos REAL,
    fornecedor TEXT
)"""
SCHEMA_DESCRIPTION = """Tabela produtos: produto TEXT, departamento TEXT, id INTEGER,
data_fabri DATE, data_venc DATE, custos REAL, fornecedor TEXT."""
MAX_SQL_LENGTH = 4000
MAX_RESULT_ROWS = 500
SQL_EXECUTION_TIMEOUT_SECONDS = 1.0
SQL_PROGRESS_INTERVAL = 1000
SAMPLE_ROWS = [
    ("sabonete", "higiene", 123, "2026-04-21", "2027-08-21", 23.50, "john"),
    ("agua", "bebidas", 234, "2026-04-22", "2029-08-22", 3.50, "lennon"),
    ("coca", "bebidas", 123, "2026-05-03", "2027-04-12", 7.00, "WOAH"),
]
GENERATOR = None


def load_env_file():
    env_file = PROJECT_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def configure_llm():
    load_env_file()
    lm = dspy.LM(
        os.getenv("LLM_MODEL", "openai/gemma-4-E2B-it-IQ4_XS"),
        api_base=os.getenv("LLM_API_BASE", "http://localhost:1337/v1"),
        api_key=os.getenv("LLM_API_KEY", "not-needed"),
    )
    dspy.configure(lm=lm)


def _connect_read_write(path=DB_PATH):
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    return connection


def create_db():
    with closing(_connect_read_write()) as connection:
        connection.execute(SCHEMA_SQL)
        for row in SAMPLE_ROWS:
            connection.execute(
                """INSERT INTO produtos
                (produto, departamento, id, data_fabri, data_venc, custos, fornecedor)
                SELECT ?, ?, ?, ?, ?, ?, ?
                WHERE NOT EXISTS (
                    SELECT 1 FROM produtos WHERE
                    produto=? AND departamento=? AND id=? AND data_fabri IS ?
                    AND data_venc IS ? AND custos IS ? AND fornecedor IS ?
                )""",
                (*row, *row),
            )
        connection.commit()


def create_in_memory_validation_db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(SCHEMA_SQL)
    connection.executemany(
        """INSERT INTO produtos
        (produto, departamento, id, data_fabri, data_venc, custos, fornecedor)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        SAMPLE_ROWS,
    )
    return connection


def is_select_only(sql):
    if not isinstance(sql, str) or not sql.strip():
        return False
    cleaned = sql.strip()
    if "--" in cleaned or "/*" in cleaned or "*/" in cleaned:
        return False
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if ";" in cleaned:
        return False
    return bool(re.match(r"^SELECT\b", cleaned, re.IGNORECASE))


def _read_only_authorizer(action_code, arg1, arg2, db_name, trigger_name):
    if action_code == sqlite3.SQLITE_FUNCTION:
        function_name = (arg2 or arg1 or "").lower()
        unsafe_functions = {"load_extension", "writefile", "readfile", "fts3_tokenizer"}
        if function_name in unsafe_functions:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ}
    return sqlite3.SQLITE_OK if action_code in allowed else sqlite3.SQLITE_DENY


def _execute_read_only(connection, sql):
    if not is_select_only(sql):
        raise ValueError("A consulta precisa ser uma única instrução SELECT.")
    if len(sql) > MAX_SQL_LENGTH:
        raise ValueError("A consulta ultrapassa o limite de tamanho.")
    connection.set_authorizer(_read_only_authorizer)
    deadline = time.monotonic() + SQL_EXECUTION_TIMEOUT_SECONDS
    connection.set_progress_handler(
        lambda: int(time.monotonic() >= deadline),
        SQL_PROGRESS_INTERVAL,
    )
    cursor = None
    try:
        cursor = connection.execute(sql)
        rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)
        if len(rows) > MAX_RESULT_ROWS:
            raise ValueError("A consulta ultrapassa o limite de linhas retornadas.")
        return rows
    finally:
        if cursor is not None:
            cursor.close()
        connection.set_progress_handler(None, 0)


class ReliableSQLGenerator(dspy.Module):
    """Gera SQL via DSPy RLM e valida segurança/sintaxe antes da consulta real."""

    def __init__(self):
        super().__init__()
        if not hasattr(dspy, "RLM"):
            raise RuntimeError("Esta versão de DSPy não oferece dspy.RLM.")
        self.generate_sql = dspy.RLM(
            "db_schema, question -> sql_query",
            max_iters=6,
            max_llm_calls=3,
            max_output_chars=3000,
        )

    def forward(self, schema, question):
        try:
            prediction = self.generate_sql(db_schema=schema, question=question)
            sql = str(prediction.sql_query).strip()
            if not is_select_only(sql):
                return dspy.Prediction(
                    sql_query=sql,
                    success=False,
                    error="A consulta gerada não é um SELECT único.",
                )
            with closing(create_in_memory_validation_db()) as validation_db:
                _execute_read_only(validation_db, sql)
            return dspy.Prediction(sql_query=sql, success=True, error=None)
        except Exception as exc:
            return dspy.Prediction(
                sql_query="",
                success=False,
                error=f"Falha ao gerar ou validar SQL: {type(exc).__name__}.",
            )


def _new_generator():
    generator = ReliableSQLGenerator()
    if MODEL_ARTIFACT.exists():
        generator.load(str(MODEL_ARTIFACT))
    return generator



def preflight():
    """Checks local runtime/configuration without printing secret values."""
    load_env_file()
    model = os.getenv("LLM_MODEL", "openai/gemma-4-E2B-it-IQ4_XS")
    base_url = os.getenv("LLM_API_BASE", "http://localhost:1337/v1").rstrip("/")
    api_key = os.getenv("LLM_API_KEY", "not-needed")
    request = Request(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"} if api_key and api_key != "not-needed" else {},
    )
    endpoint_available = False
    model_ids = []
    error_type = None
    try:
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        model_ids = [
            item["id"] for item in payload.get("data", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ]
        endpoint_available = True
    except Exception as exc:
        error_type = type(exc).__name__

    requested_model = model.rsplit("/", 1)[-1]
    model_available = (
        any(model_id in {model, requested_model} for model_id in model_ids)
        if endpoint_available
        else None
    )
    deno_path = Path(sys.executable).with_name("deno")
    telegram_configured = bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip())
    transcription_url = os.getenv("VOICE_TRANSCRIPTION_URL", "").strip()
    transcription_key_configured = bool(os.getenv("VOICE_TRANSCRIPTION_API_KEY", "").strip())
    wip = []
    if not endpoint_available:
        wip.append("Iniciar o endpoint LLM configurado.")
    if model_available is not True:
        wip.append("Confirmar LLM_MODEL contra o ID servido em /v1/models.")
    if not telegram_configured:
        wip.append("Configurar TELEGRAM_BOT_TOKEN.")
    if not transcription_url:
        wip.append("Configurar VOICE_TRANSCRIPTION_URL.")
    else:
        wip.append("Validar VOICE_TRANSCRIPTION_URL com uma transcrição real.")
    return {
        "runtime": {
            "dspy_rlm": hasattr(dspy, "RLM"),
            "dspy_gepa": hasattr(dspy, "GEPA"),
            "deno_binary": deno_path.is_file(),
        },
        "llm": {
            "base_url": base_url,
            "model": model,
            "endpoint_available": endpoint_available,
            "model_available": model_available,
            "served_model_ids": model_ids,
            "error_type": error_type,
        },
        "telegram": {"token_configured": telegram_configured},
        "transcription": {
            "url_configured": bool(transcription_url),
            "api_key_configured": transcription_key_configured,
            "endpoint_validation": "pending",
        },
        "wip": wip,
    }


def initialize_services():
    global GENERATOR
    load_env_file()
    create_db()
    configure_llm()
    GENERATOR = _new_generator()


def generate(question):
    if not isinstance(question, str) or not question.strip():
        return {
            "success": False,
            "error": "Informe uma pergunta.",
            "error_code": "invalid_question",
            "results": None,
        }
    if GENERATOR is None:
        return {
            "success": False,
            "error": "O gerador ainda não foi inicializado.",
            "error_code": "not_ready",
            "results": None,
        }
    try:
        result = GENERATOR(schema=SCHEMA_DESCRIPTION, question=question.strip())
    except Exception:
        return {
            "success": False,
            "error": "O serviço de geração está temporariamente indisponível.",
            "error_code": "generation_failed",
            "results": None,
        }
    if not result.success:
        return {
            "success": False,
            "error": result.error,
            "error_code": "generation_failed",
            "results": None,
        }
    try:
        db_uri = f"file:{quote(str(DB_PATH), safe='/')}?mode=ro"
        with closing(sqlite3.connect(db_uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            rows = _execute_read_only(connection, result.sql_query)
        records = [dict(row) for row in rows]
    except (sqlite3.Error, ValueError):
        return {
            "success": False,
            "error": "A consulta falhou na validação de leitura.",
            "error_code": "database_error",
            "results": None,
        }
    if not records:
        return {"success": False, "error": "Nenhum produto encontrado.", "results": []}
    return {"success": True, "error": None, "results": records}


def _evaluation_examples():
    return [
        ("Qual o departamento do sabonete?", "SELECT departamento FROM produtos WHERE produto = 'sabonete'", [("higiene",)]),
        ("Quais produtos são do departamento bebidas?", "SELECT produto FROM produtos WHERE departamento = 'bebidas' ORDER BY produto", [("agua",), ("coca",)]),
        ("Qual o custo do sabonete?", "SELECT custos FROM produtos WHERE produto = 'sabonete'", [(23.5,)]),
        ("Qual fornecedor entrega coca?", "SELECT fornecedor FROM produtos WHERE produto = 'coca'", [("WOAH",)]),
        ("Quais produtos vencem depois de 2028-01-01?", "SELECT produto FROM produtos WHERE data_venc > '2028-01-01' ORDER BY produto", [("agua",)]),
        ("Liste os produtos e departamentos em estoque.", "SELECT produto, departamento FROM produtos ORDER BY produto", [("agua", "bebidas"), ("coca", "bebidas"), ("sabonete", "higiene")]),
        ("Existe produto chamado inexistente?", "SELECT produto FROM produtos WHERE produto = 'inexistente'", []),
    ]


def _metric(example, prediction, trace=None):
    sql = str(getattr(prediction, "sql_query", ""))
    if not is_select_only(sql):
        return dspy.Prediction(score=0.0, feedback="Rejeitar: saída não é um SELECT único.")
    try:
        with closing(create_in_memory_validation_db()) as connection:
            actual = [tuple(row) for row in _execute_read_only(connection, sql)]
        expected = [tuple(row) for row in example.expected_rows]
        score = 1.0 if actual == expected else 0.0
        feedback = "Resultado correto." if score else f"Resultado incorreto; esperado {expected}, obtido {actual}."
        return dspy.Prediction(score=score, feedback=feedback)
    except Exception as exc:
        return dspy.Prediction(score=0.0, feedback=f"SQL rejeitado: {type(exc).__name__}.")


def evaluate_safety_results():
    """Avalia consultas SQL conhecidas e bloqueios sem chamar um modelo."""
    known_cases = []
    for question, sql, expected in _evaluation_examples():
        try:
            with closing(create_in_memory_validation_db()) as connection:
                actual = [tuple(row) for row in _execute_read_only(connection, sql)]
            known_cases.append({
                "question": question,
                "correct": actual == expected,
            })
        except (sqlite3.Error, ValueError):
            known_cases.append({"question": question, "correct": False})

    adversarial = [
        "INSERT INTO produtos VALUES (1)",
        "UPDATE produtos SET produto='x'",
        "DELETE FROM produtos",
        "DROP TABLE produtos",
        "SELECT 1; DELETE FROM produtos",
        "SELECT FROM",
        "SELECT load_extension('x')",
    ]
    rejected = 0
    unchanged = True
    for sql in adversarial:
        with closing(create_in_memory_validation_db()) as connection:
            before = connection.execute("SELECT COUNT(*) FROM produtos").fetchone()[0]
            try:
                _execute_read_only(connection, sql)
            except (sqlite3.Error, ValueError):
                rejected += 1
            after = connection.execute("SELECT COUNT(*) FROM produtos").fetchone()[0]
            unchanged = unchanged and before == after

    return {
        "mode": "offline_sql_safety_and_known_queries",
        "known_query_cases": known_cases,
        "known_query_accuracy": sum(case["correct"] for case in known_cases) / len(known_cases),
        "adversarial_rejected": rejected,
        "adversarial_total": len(adversarial),
        "validation_data_unchanged": unchanged,
    }


def _evaluate_generator(generator):
    outcomes = []
    for question, sql, expected in _evaluation_examples():
        prediction = generator(schema=SCHEMA_DESCRIPTION, question=question)
        safe = bool(prediction.success and is_select_only(prediction.sql_query))
        correct = False
        if safe:
            try:
                with closing(create_in_memory_validation_db()) as connection:
                    actual = [tuple(row) for row in _execute_read_only(connection, prediction.sql_query)]
                correct = actual == expected
            except sqlite3.Error:
                pass
        outcomes.append({"question": question, "safe_select": safe, "correct": correct})
    return {
        "cases": outcomes,
        "correct_rate": sum(item["correct"] for item in outcomes) / len(outcomes),
        "safe_query_rate": sum(item["safe_select"] for item in outcomes) / len(outcomes),
    }


def evaluate_results():
    baseline = ReliableSQLGenerator()
    candidate = _new_generator()
    adversarial = [
        "INSERT INTO produtos VALUES (1)",
        "UPDATE produtos SET produto='x'",
        "DELETE FROM produtos",
        "DROP TABLE produtos",
        "SELECT 1; DELETE FROM produtos",
        "SELECT FROM",
    ]
    rejected = 0
    unchanged = True
    for sql in adversarial:
        with closing(create_in_memory_validation_db()) as connection:
            before = connection.execute("SELECT COUNT(*) FROM produtos").fetchone()[0]
            try:
                _execute_read_only(connection, sql)
            except (sqlite3.Error, ValueError):
                rejected += 1
            after = connection.execute("SELECT COUNT(*) FROM produtos").fetchone()[0]
            unchanged = unchanged and before == after
    return {
        "baseline": _evaluate_generator(baseline),
        "optimized_or_current": _evaluate_generator(candidate),
        "adversarial_rejected": rejected,
        "adversarial_total": len(adversarial),
        "validation_database_unchanged": unchanged,
    }


def optimize_generator():
    configure_llm()
    examples = [
        dspy.Example(
            schema=SCHEMA_DESCRIPTION,
            question=question,
            sql_query=sql,
            expected_rows=expected,
        ).with_inputs("schema", "question")
        for question, sql, expected in _evaluation_examples()[:-1]
    ]
    student = ReliableSQLGenerator()
    optimizer = dspy.GEPA(metric=_metric, auto="light", track_stats=True)
    optimized = optimizer.compile(student, trainset=examples, valset=examples)
    optimized.save(str(MODEL_ARTIFACT))
    return str(MODEL_ARTIFACT)


@asynccontextmanager
async def lifespan(app):
    initialize_services()
    yield


app = FastAPI(title="Bot de Estoque Inteligente", lifespan=lifespan)


@app.get("/query")
def query_stock(question: str = Query(..., min_length=1, max_length=500)):
    result = generate(question)
    error_status = {
        "invalid_question": 400,
        "not_ready": 503,
        "generation_failed": 502,
        "database_error": 500,
    }
    status_code = error_status.get(result.get("error_code"))
    if status_code:
        raise HTTPException(status_code=status_code, detail=result["error"])
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--optimize", action="store_true")
    parser.add_argument("--preflight", action="store_true", help="Verifica serviços configurados sem exibir segredos.")
    parser.add_argument("--evaluate", action="store_true", help="Avalia com o gerador e requer o serviço LLM.")
    parser.add_argument("--evaluate-safety", action="store_true", help="Avalia SQL conhecido e bloqueios sem LLM.")
    args = parser.parse_args()
    if args.preflight:
        print(json.dumps(preflight(), ensure_ascii=False, indent=2))
    elif args.evaluate_safety:
        print(json.dumps(evaluate_safety_results(), ensure_ascii=False, indent=2))
    elif args.optimize:
        initialize_services()
        print(json.dumps({"artifact": optimize_generator()}, ensure_ascii=False))
    elif args.evaluate:
        initialize_services()
        print(json.dumps(evaluate_results(), ensure_ascii=False, indent=2))
    else:
        parser.print_help()
