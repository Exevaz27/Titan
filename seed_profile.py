#!/usr/bin/env python3
"""Carga por única vez el perfil de Exequiel en la memoria a largo plazo de Titán.

Uso (en la DDR3, desde la raíz del repo, con Titán detenido):
    .venv/bin/python seed_profile.py

- El perfil (nombre, cumpleaños, zona, etc.) se inyecta en CADA prompt.
- Los recuerdos se buscan por relevancia según lo que se hable.
- Es idempotente: se puede correr de nuevo sin duplicar (actualiza).
- Después de correrlo podés borrar este archivo (o no commitearlo si no
  querés tus datos personales en el repo de GitHub).
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.memory import titan_memory

# Perfil: va en TODOS los prompts. Solo lo esencial y de uso frecuente.
PROFILE = {
    "name": "Exequiel",
    "cumpleanos": "27/08/1997",
    "zona": "Barrio La Matera, Solano, Quilmes Oeste",
    "novia": "Oriana (de novios desde el 8/12/2020)",
    "equipo": "Boca Juniors",
    "ocupacion": "Emprendimiento de impresiones 3D; estudiando para entrar a Solec (tercerizada de Edesur, cambiar postes de luz)",
}

# Recuerdos: (clave, contenido, categoría). Se recuperan por relevancia.
MEMORIES = [
    ("familia_madre",
     "Vive en casa aparte en el terreno de su vieja Vero. Vero vive con su marido Kito y sus hermanos Lautaro (21) y Agus 'Cache' (17).",
     "familia"),
    ("familia_padre",
     "Su viejo Edu vive con su mujer Faty, sus hermanas Mia (16) y Valen (11), y sus hermanos Nico (8) y Bruno (4).",
     "familia"),
    ("amigos",
     "Sus amigos cercanos son Gaston y Chamo. Su primo Antonio (17) va a su casa casi siempre.",
     "gente"),
    ("mascotas",
     "En su casa hay dos perras: Lupita y Bianca, y un gato al que le dice Mish porque nunca se acuerda el nombre.",
     "mascotas"),
    ("musica",
     "Le gusta el rock nacional, la cumbia romantica, santafesina, villera y base (lo que mas), el cuarteto, el rap/hip hop y la romantica variada. Escucha casi todo de antes, poco actual.",
     "gustos"),
    ("anime_series",
     "Su anime favorito es Dragon Ball. Mira series y peliculas de todos los generos.",
     "gustos"),
    ("comida",
     "Esquiva las verduras y las sopas. Le encanta la carne, el asado, las milanesas, la pizza y las empanadas fritas. Es fan del tuco (salsa roja) con todo: fideos, arroz, lo que sea.",
     "gustos"),
    ("bebidas",
     "Fan del mate 24/7. Tambien toma te, cafe y mate cocido. Toma poco alcohol; sus favoritos son el vino y el fernet.",
     "gustos"),
    ("auto",
     "Tiene un Chevrolet Corsa del 99.",
     "datos"),
    ("plataformas",
     "Ve YouTube en la PC, recien empezo a usar Spotify. Para peliculas usa Xuper TV o Cloudstream.",
     "gustos"),
    ("futbol5",
     "Juega futbol 5 de defensor, sin dias ni horarios fijos. Es capaz de dejar todo por ir a jugar un partidito, aunque este enfermo o lastimado.",
     "deporte"),
    ("estudio_solec",
     "Esta estudiando unas preguntas que le dieron y practicando rescate para entrar a Solec. Cuando arranque se tiene que levantar a las 5am.",
     "trabajo"),
    ("impresoras_3d",
     "Su emprendimiento de impresiones 3D tiene 1 Ender 3 V2 y 2 Ender 3 V3 SE.",
     "trabajo"),
    ("sueno",
     "Duerme mal, sin horarios fijos: a veces se duerme tarde y se levanta tarde, o al reves. Quiere acomodar el suenio antes de arrancar el trabajo.",
     "salud"),
    ("videojuegos_tecnologia",
     "Le gustan los videojuegos y la tecnologia.",
     "gustos"),
    ("programacion_diseno",
     "Le atrae mucho la programacion y el disenio, aunque todavia no sabe nada del tema.",
     "intereses"),
    ("ia",
     "Le atrae el tema de la IA y sus usos.",
     "intereses"),
]


def main() -> None:
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    with titan_memory._get_conn() as conn:
        for k, v in PROFILE.items():
            conn.execute(
                "INSERT OR REPLACE INTO profile (key, value, updated_at) VALUES (?, ?, ?)",
                (k, v, now_str),
            )
        conn.commit()
    print(f"[Seed] perfil: {len(PROFILE)} entradas")

    for key, value, category in MEMORIES:
        titan_memory.remember(key, value, category)
        print(f"[Seed] recuerdo: {key}")

    print("[Seed] listo. Titán ya te conoce.")


if __name__ == "__main__":
    main()
