import sqlite3
import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
from core.logger import log_info, log_error, log_warning
from core.config import config

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "titan_memory.db"
JSON_BACKUP = Path(__file__).resolve().parent.parent / "memory.json"

class TitanMemory:
    """
    Sistema de Memoria a Largo Plazo para Titán Asistente.
    Combina persistencia relacional en SQLite con búsqueda semántica vectorial
    mediante Google Gemini Embeddings (gemini-embedding-2) y cálculo de similitud coseno.
    """
    def __init__(self, db_path: Path = DB_PATH, json_backup: Path = JSON_BACKUP):
        self.db_path = db_path
        self.json_backup = json_backup
        self._genai_client = None
        self._init_db()
        self._migrate_if_needed()

    def _get_client(self):
        if self._genai_client is None and config.gemini_api_key:
            try:
                from google import genai
                self._genai_client = genai.Client(api_key=config.gemini_api_key)
            except Exception as e:
                log_warning(f"[Memoria] No se pudo inicializar cliente Gemini para embeddings: {e}")
        return self._genai_client

    def _get_conn(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Crea las tablas de SQLite si no existen"""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS profile (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL DEFAULT 'general',
                        key TEXT NOT NULL,
                        content TEXT NOT NULL,
                        embedding BLOB,
                        created_at TEXT NOT NULL,
                        last_accessed TEXT NOT NULL,
                        importance INTEGER DEFAULT 1
                    )
                """)
                cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_key ON memories(key)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_cat ON memories(category)")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS notes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        text TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        completed INTEGER DEFAULT 0
                    )
                """)
                conn.commit()
        except Exception as e:
            log_error(f"[Memoria] Error inicializando base de datos SQLite: {e}")

    def _migrate_if_needed(self):
        """Migra recuerdos existentes de memory.json a SQLite si la base está vacía"""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) as cnt FROM memories")
                count = cur.fetchone()["cnt"]
                if count > 0:
                    return

                if self.json_backup.exists():
                    log_info("[Memoria] Migrando recuerdos antiguos desde memory.json a SQLite...")
                    with open(self.json_backup, "r", encoding="utf-8") as f:
                        old_data = json.load(f)

                    profile = old_data.get("profile", {})
                    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
                    for k, v in profile.items():
                        cur.execute("INSERT OR REPLACE INTO profile (key, value, updated_at) VALUES (?, ?, ?)", (k, str(v), now_str))

                    memories = old_data.get("memories", {})
                    for k, v in memories.items():
                        emb_blob = self._compute_embedding_blob(f"{k}: {v}")
                        cur.execute("""
                            INSERT INTO memories (category, key, content, embedding, created_at, last_accessed, importance)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, ("preferencia", k, str(v), emb_blob, now_str, now_str, 2))

                    notes = old_data.get("notes", [])
                    for n in notes:
                        cur.execute("INSERT INTO notes (text, created_at, completed) VALUES (?, ?, 0)", (n.get("text", ""), n.get("date", now_str)))

                    conn.commit()
                    log_info(f"[Memoria] ✅ Migración completada: {len(memories)} recuerdos y {len(notes)} notas cargadas en SQLite.")
                else:
                    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
                    cur.execute("INSERT OR IGNORE INTO profile (key, value, updated_at) VALUES ('name', 'Eze', ?)", (now_str,))
                    cur.execute("INSERT OR IGNORE INTO profile (key, value, updated_at) VALUES ('favorite_team', 'Boca Juniors', ?)", (now_str,))
                    cur.execute("INSERT OR IGNORE INTO profile (key, value, updated_at) VALUES ('city', 'Buenos Aires', ?)", (now_str,))
                    conn.commit()
        except Exception as e:
            log_error(f"[Memoria] Error durante migración a SQLite: {e}")

    def _compute_embedding_blob(self, text: str) -> Optional[bytes]:
        """Calcula el vector embedding usando Gemini y lo empaqueta como bytes para SQLite"""
        vec = self._get_embedding(text)
        if vec is not None:
            return vec.astype(np.float32).tobytes()
        return None

    def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Llama a la API de Google Embeddings para obtener el vector semántico"""
        client = self._get_client()
        if not client:
            return None

        models_to_try = [
            "gemini-embedding-2",
            "models/gemini-embedding-2",
            "gemini-embedding-001",
            "models/gemini-embedding-001"
        ]

        for m in models_to_try:
            try:
                res = client.models.embed_content(model=m, contents=text)
                if hasattr(res, "embeddings") and res.embeddings:
                    values = res.embeddings[0].values
                    return np.array(values, dtype=np.float32)
                elif hasattr(res, "embedding") and res.embedding:
                    values = res.embedding.values if hasattr(res.embedding, "values") else res.embedding
                    return np.array(values, dtype=np.float32)
            except Exception:
                continue
        return None

    @staticmethod
    def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """Calcula la similitud coseno entre dos vectores"""
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))

    def remember(self, key: str, value: str, category: str = "general") -> str:
        """Guarda un recuerdo clave o preferencia a largo plazo con embedding semántico"""
        clean_key = key.strip().lower()
        clean_val = value.strip()
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        emb_blob = self._compute_embedding_blob(f"{clean_key}: {clean_val}")

        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id FROM memories WHERE key = ?", (clean_key,))
                existing = cur.fetchone()
                if existing:
                    cur.execute("""
                        UPDATE memories
                        SET content = ?, category = ?, embedding = ?, last_accessed = ?
                        WHERE id = ?
                    """, (clean_val, category, emb_blob, now_str, existing["id"]))
                else:
                    cur.execute("""
                        INSERT INTO memories (category, key, content, embedding, created_at, last_accessed, importance)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (category, clean_key, clean_val, emb_blob, now_str, now_str, 2))
                conn.commit()

            self._sync_to_json_backup()
            log_info(f"[Memoria SQLite] Recordando '{clean_key}': {clean_val} (vector embedding: {'OK' if emb_blob else 'OFFLINE'})")
            return f"Listo, papá. Me lo guardo en la memoria permanente: '{clean_key}' es '{clean_val}'."
        except Exception as e:
            log_error(f"[Memoria] Error guardando recuerdo '{clean_key}': {e}")
            return f"Tuve un problema guardando el recuerdo: {e}"

    def search_memories(self, query: str, top_k: int = 4, min_score: float = 0.48) -> List[Dict[str, Any]]:
        """Busca recuerdos semánticos mediante embeddings de Gemini + similitud coseno"""
        clean_q = query.strip()
        if not clean_q:
            return []

        query_vec = self._get_embedding(clean_q)
        q_lower = clean_q.lower()

        results = []
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id, category, key, content, embedding, created_at FROM memories")
                rows = cur.fetchall()

                for r in rows:
                    key = r["key"]
                    content = r["content"]
                    emb_bytes = r["embedding"]

                    text_score = 0.0
                    if key.lower() in q_lower or q_lower in key.lower():
                        text_score = 0.95
                    elif any(word in content.lower() for word in q_lower.split() if len(word) > 3):
                        text_score = 0.65

                    sem_score = 0.0
                    if query_vec is not None and emb_bytes:
                        try:
                            mem_vec = np.frombuffer(emb_bytes, dtype=np.float32)
                            if len(mem_vec) == len(query_vec):
                                sem_score = self._cosine_similarity(query_vec, mem_vec)
                        except Exception:
                            pass

                    final_score = max(sem_score, text_score) if not sem_score else (sem_score * 0.75 + text_score * 0.25)

                    if final_score >= min_score:
                        results.append({
                            "id": r["id"],
                            "category": r["category"],
                            "key": key,
                            "content": content,
                            "score": round(final_score, 3)
                        })

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]
        except Exception as e:
            log_error(f"[Memoria] Error en búsqueda semántica: {e}")
            return []

    def recall(self, query: str) -> str:
        """Recupera un recuerdo específico buscando por similitud semántica o clave"""
        matches = self.search_memories(query, top_k=3, min_score=0.45)
        if matches:
            top = matches[0]
            if len(matches) == 1 or top["score"] > 0.70:
                return f"Lo que me acuerdo de '{top['key']}': {top['content']}"
            else:
                lines = ["Acá encontré lo que tengo guardado sobre eso:"]
                for m in matches:
                    lines.append(f"• {m['key']}: {m['content']}")
                return "\n".join(lines)
        return f"No tengo nada guardado sobre '{query}', che."

    def list_all_memories(self) -> str:
        """Lista todos los recuerdos y perfil guardados en la base SQLite"""
        try:
            lines = []
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT key, value FROM profile ORDER BY key")
                profile_rows = cur.fetchall()
                if profile_rows:
                    lines.append("👤 Perfil:")
                    for r in profile_rows:
                        lines.append(f"• {r['key']}: {r['value']}")

                cur.execute("SELECT category, key, content FROM memories ORDER BY category, key")
                mem_rows = cur.fetchall()
                if mem_rows:
                    lines.append("\n🧠 Recuerdos guardados:")
                    for r in mem_rows:
                        lines.append(f"• [{r['category']}] {r['key']}: {r['content']}")

                cur.execute("SELECT COUNT(*) as total FROM notes WHERE completed = 0")
                notes_count = cur.fetchone()["total"]
                if notes_count > 0:
                    lines.append(f"\n📝 Notas activas: {notes_count} pendientes.")

            if not lines:
                return "Todavía no tengo nada guardado en mi memoria permanente."
            return "\n".join(lines)
        except Exception as e:
            return f"Error leyendo memoria: {e}"

    def add_note(self, text: str) -> str:
        """Agrega una nota o pendiente a la base de datos"""
        now_str = time.strftime("%d/%m %H:%M")
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("INSERT INTO notes (text, created_at, completed) VALUES (?, ?, 0)", (text.strip(), now_str))
                note_id = cur.lastrowid
                conn.commit()
            self._sync_to_json_backup()
            log_info(f"[Memoria] Nueva nota #{note_id}: {text}")
            return f"Anotadísimo: '{text}' (Nota #{note_id})."
        except Exception as e:
            return f"Error anotando: {e}"

    def get_notes(self) -> str:
        """Devuelve todas las notas y recordatorios pendientes"""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT id, created_at, text FROM notes WHERE completed = 0 ORDER BY id ASC")
                rows = cur.fetchall()

            if not rows:
                return "No tenés ninguna nota guardada por ahora, fiera."
            lines = ["📝 Tus notas y recordatorios pendientes:"]
            for r in rows:
                lines.append(f"#{r['id']}: [{r['created_at']}] {r['text']}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error consultando notas: {e}"

    def delete_note(self, note_id_or_text: str) -> str:
        """Elimina una nota por su número de ID o texto coincidente"""
        query = note_id_or_text.strip()
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                if query.isdigit():
                    cur.execute("DELETE FROM notes WHERE id = ?", (int(query),))
                else:
                    cur.execute("DELETE FROM notes WHERE text LIKE ?", (f"%{query}%",))
                deleted = cur.rowcount
                conn.commit()

            self._sync_to_json_backup()
            if deleted > 0:
                return f"Listo, borré la nota '{note_id_or_text}', papá."
            return f"No encontré ninguna nota que coincida con '{note_id_or_text}'."
        except Exception as e:
            return f"Error borrando nota: {e}"

    def get_prompt_context(self, query_text: str = "") -> str:
        """
        Genera el fragmento de texto con la memoria para alimentar el system prompt.
        Ultra-optimizado para respuesta instantánea (<1ms):
        Lee directamente de SQLite sin hacer llamadas remotas de red a la API de embeddings.
        """
        parts = []
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT key, value FROM profile")
                profile = {r["key"]: r["value"] for r in cur.fetchall()}
                if profile:
                    prof_str = ", ".join(f"{k}: {v}" for k, v in profile.items() if v)
                    parts.append(f"Perfil de fondo: {prof_str} (RECORDATORIO: No uses su nombre como saludo repetitivo; hablale con confianza de compinche)")

                cur.execute("SELECT key, content FROM memories ORDER BY importance DESC, last_accessed DESC LIMIT 15")
                all_mems = cur.fetchall()

                if all_mems:
                    if len(all_mems) <= 10:
                        # Con pocos recuerdos (<10), inyectarlos directamente toma <0.5ms y consume mínimos tokens
                        mem_strs = [f"{r['key']}: {r['content']}" for r in all_mems]
                        parts.append(f"Recuerdos guardados: {'; '.join(mem_strs)}")
                    else:
                        # Si hay muchos recuerdos, priorizamos por coincidencia de palabras clave rápida en memoria local
                        q_lower = (query_text or "").lower()
                        words = [w for w in q_lower.split() if len(w) > 3]
                        matched = []
                        unmatched = []
                        for r in all_mems:
                            k_lower = r["key"].lower()
                            c_lower = r["content"].lower()
                            if k_lower in q_lower or any(w in k_lower or w in c_lower for w in words):
                                matched.append(f"{r['key']}: {r['content']}")
                            else:
                                unmatched.append(f"{r['key']}: {r['content']}")

                        selected = (matched + unmatched)[:8]
                        parts.append(f"Recuerdos clave: {'; '.join(selected)}")

            if not parts:
                return ""
            return " | ".join(parts)
        except Exception as e:
            log_error(f"[Memoria] Error armando prompt context: {e}")
            return ""

    def _sync_to_json_backup(self):
        """Mantiene un espejo en memory.json como copia de seguridad legible"""
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT key, value FROM profile")
                profile = {r["key"]: r["value"] for r in cur.fetchall()}

                cur.execute("SELECT key, content FROM memories")
                memories = {r["key"]: r["content"] for r in cur.fetchall()}

                cur.execute("SELECT id, created_at, text FROM notes WHERE completed = 0")
                notes = [{"id": r["id"], "date": r["created_at"], "text": r["text"]} for r in cur.fetchall()]

            data = {
                "profile": profile,
                "memories": memories,
                "notes": notes
            }
            with open(self.json_backup, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

titan_memory = TitanMemory()
