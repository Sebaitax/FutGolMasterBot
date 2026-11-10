"""Narración del partido a partir de los eventos del motor.

Cada jugada se arma combinando una "preparación" (cómo se construyó) con un
"final" (gol, atajada, desviado, palo), con varias versiones de cada uno y
comentarios según el contexto (empate, remontada, doblete, gol sobre la hora…).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from partidos.motor import Evento, Resultado

# ------------------------------------------------------------ preparaciones
# {tir} = quien remata, {asis} = quien asiste

PREPARACION = {
    "centro": [
        "{asis} corre por la banda, levanta la cabeza y mete el centro al área para {tir}",
        "{asis} desborda por la banda y tira el centro buscando a {tir}",
        "Centro rasante de {asis} desde la banda, {tir} llega a la carrera",
        "{asis} se escapa por la orilla y la cruza al punto penal para {tir}",
    ],
    "centro_cabeza": [
        "{asis} levanta un centro desde la banda y {tir} se eleva entre los centrales",
        "Centro de {asis} al segundo palo, {tir} gana en el salto",
        "{asis} la manda pasada al área y {tir} cabecea con todo",
    ],
    "contragolpe": [
        "¡Contragolpe! {asis} recupera y lanza a {tir}, que corre solo hacia el arco",
        "Salida rápida: {asis} habilita a {tir} en velocidad y nadie lo alcanza",
        "{tir} pica al espacio tras el pelotazo largo de {asis}",
    ],
    "pared": [
        "{tir} tira la pared con {asis} y entra al área",
        "Toque-toque entre {asis} y {tir} en la puerta del área",
        "{asis} la devuelve de primera y {tir} queda de frente al arco",
    ],
    "pase_filtrado": [
        "Pase filtrado de {asis} entre los centrales para {tir}",
        "{asis} ve el desmarque de {tir} y le pone la pelota al espacio",
        "Qué pase de {asis}: deja a {tir} mano a mano",
    ],
    "individual": [
        "{tir} encara, deja a uno en el camino y se mete al área",
        "Jugada individual de {tir}: amague, gambeta, otra más y remate",
        "{tir} arranca desde mitad de cancha, nadie lo puede parar",
    ],
    "lejano": [
        "{tir} se perfila desde fuera del área y saca el remate",
        "{tir} prueba de media distancia",
        "¡Zapatazo de {tir} desde lejos!",
    ],
    "rebote": [
        "La pelota queda boteando en el área y {tir} llega primero",
        "Rebote en la defensa y le queda servida a {tir}",
        "Se arma un lío en el área chica, {tir} saca el remate",
    ],
    "penal": [
        "{tir} toma carrera desde los once metros",
        "{tir} acomoda la pelota en el punto penal… silencio en el estadio",
    ],
}

FINAL = {
    "gol": [
        "… ¡GOOOOL de {tir}!",
        "… ¡y adentro! {tir} no perdona.",
        "… ¡GOL! La manda al fondo de la red.",
        "… ¡la clavó en el ángulo! Gol de {tir}.",
    ],
    "gol_cabeza": [
        "… ¡GOL de cabeza de {tir}!",
        "… ¡testazo y adentro! Gol de {tir}.",
    ],
    "gol_penal": [
        "… ¡GOL! Engaña a {por} y la pone junto al palo.",
        "… ¡adentro! {por} se tira para el otro lado.",
    ],
    "atajada": [
        "… pero aparece {por} con una tremenda atajada.",
        "… ¡{por} vuela y la saca!",
        "… {por} la contiene sin problemas.",
        "… ¡manotazo de {por} para salvar a su equipo!",
    ],
    "atajada_penal": [
        "… ¡LO ATAJÓ {por}! Adivinó el lado.",
        "… ¡{por} se queda con el penal!",
    ],
    "desviado": [
        "… pero se va desviado.",
        "… la pelota pasa rozando el palo.",
        "… se le fue por arriba del travesaño.",
        "… le pega mal y se va lejos.",
    ],
    "desviado_penal": [
        "… ¡y lo tira afuera! Increíble.",
        "… ¡por encima del travesaño! Se perdió el penal.",
    ],
    "palo": [
        "… ¡y la pelota pega en el palo!",
        "… ¡PALO! Se salvó {rival}.",
        "… ¡al travesaño! Qué cerca estuvo.",
    ],
}

CONTEXTO_GOL = {
    "primero": ["{equipo} abre el marcador.", "¡Se rompe el cero!"],
    "empate": ["¡{equipo} lo empata!", "Todo igualado otra vez."],
    "ventaja": ["{equipo} se pone en ventaja.", "¡{equipo} da vuelta el partido!"],
    "amplia": ["{equipo} amplía la diferencia.", "{equipo} se aleja en el marcador."],
    "descuento": ["{equipo} descuenta y se ilusiona.", "Hay partido: {equipo} se acerca."],
    "tarde": ["¡Sobre la hora!", "¡En el último suspiro!"],
    "doblete": ["¡Doblete para {tir}!", "{tir} anota su segundo de la tarde."],
    "triplete": ["¡TRIPLETE de {tir}! Se lleva la pelota a casa.", "¡Hat-trick de {tir}!"],
    "golazo": ["¡QUÉ GOLAZO!", "¡Un golazo de otro planeta!"],
}

SIMPLES = {
    "falta": [
        "Falta de {jug} para cortar el avance.",
        "{jug} llega tarde y comete falta.",
        "Infracción de {jug} en mitad de cancha.",
    ],
    "amarilla": [
        "Tarjeta amarilla para {jug} por una entrada fuerte.",
        "El árbitro amonesta a {jug}.",
        "{jug} ve la amarilla por protestar.",
        "Amarilla a {jug} por cortar el contragolpe.",
    ],
    "roja_directa": [
        "¡ROJA DIRECTA para {jug}! Entrada criminal y {equipo} se queda con diez.",
        "¡Expulsado {jug}! Patada sin pelota, roja directa.",
    ],
    "roja_doble": [
        "Segunda amarilla para {jug}… ¡y se va expulsado!",
        "{jug} vuelve a pegar, segunda amarilla y roja. {equipo} con uno menos.",
    ],
    "lesion": [
        "{jug} se queda tendido en el césped… entra la asistencia médica. Parece serio.",
        "Mala noticia para {equipo}: {jug} se resiente y no puede seguir.",
        "{jug} pide el cambio, se toma la pierna. Lesionado.",
    ],
    "cambio_tactico": [
        "Cambio en {equipo}: sale {sale}, entra {jug}.",
        "{equipo} mueve el banco: {jug} por un cansado {sale}.",
        "Entra {jug} en lugar de {sale}.",
    ],
    "cambio_decision": [
        "Cambio en {equipo}: sale {sale}, entra {jug}.",
        "El DT de {equipo} mueve las piezas: {jug} reemplaza a {sale}.",
        "Ingresa {jug} en {equipo}; se va {sale}.",
    ],
    "cambio_tras_roja": [
        "{equipo} se reacomoda tras la expulsión: entra {jug}, sale {sale}.",
        "Con diez, {equipo} ordena la cancha: {jug} por {sale}.",
    ],
    "cambio_lesion": [
        "Entra {jug} por el lesionado {sale}.",
        "{sale} sale en camilla, en su lugar entra {jug}.",
    ],
    "al_arco": [
        "¡Sin cambios disponibles, {jug} se pone los guantes y va al arco!",
    ],
    "penal": [
        "¡PENAL para {equipo}! Derriban a un jugador dentro del área.",
        "¡El árbitro cobra penal a favor de {equipo}!",
    ],
    "momento": [
        "¡Atención! {jug} queda de frente al arco…",
        "¡Se viene! {jug} recibe en zona de peligro…",
        "¡Ojo! {jug} se perfila en el área…",
    ],
    "perdida_pase": [
        "{jug} intenta el pase a {otro}, pero la defensa lo corta.",
        "{jug} busca a {otro}… ¡interceptado!",
    ],
    "perdida_gambeta": [
        "{jug} encara a {otro}… ¡y {otro} se la quita limpio!",
        "{jug} intenta la gambeta, pero {otro} no se come el amague.",
    ],
    "adicion": [
        "El cuarto árbitro levanta el cartel: {min_add} de adición.",
        "Se jugará{n} {min_add} más.",
    ],
}

TACTICA = {
    "presion": "{equipo} adelanta las líneas y sale a presionar arriba.",
    "contragolpe": "{equipo} retrocede y espera para salir de contragolpe.",
    "centros": "{equipo} abre la cancha y empieza a tirar centros al área.",
    "cuidar": "{equipo} se cierra atrás para cuidar el resultado.",
    "normal": "{equipo} vuelve a su esquema habitual.",
}
LADO = {"izq": "a la izquierda", "centro": "al medio", "der": "a la derecha"}

RELLENO = [
    "{equipo} mueve la pelota con paciencia buscando espacios.",
    "Partido trabado en el medio, mucha fricción.",
    "{equipo} presiona arriba y no deja salir al rival.",
    "Se escucha a la hinchada de {equipo}.",
    "{equipo} intenta por las bandas, pero la defensa está bien parada.",
    "Ritmo intenso, ida y vuelta en ambas áreas.",
]

EMOJI = {
    "gol": "⚽", "atajada": "🧤", "desviado": "💨", "palo": "🥅", "falta": "⚠️",
    "amarilla": "🟨", "roja": "🟥", "lesion": "🚑", "cambio": "🔄", "al_arco": "🧤",
    "penal": "❗", "adicion": "⏱️", "relleno": "🎙️", "momento": "🎯", "perdida": "❌", "tactica": "🧠",
}


@dataclass
class Linea:
    minuto: str
    texto: str
    tipo: str
    min: int = 0          # minuto numérico (para sincronizar animaciones)
    tiempo: int = 1
    equipo: int = -1
    extra: dict = field(default_factory=dict)

    def a_dict(self) -> dict:
        return {"minuto": self.minuto, "texto": self.texto, "tipo": self.tipo, "min": self.min,
                "tiempo": self.tiempo, "equipo": self.equipo, **self.extra}

    def __str__(self) -> str:
        if not self.minuto:
            return self.texto
        return f"**{self.minuto}** {EMOJI.get(self.tipo, '')} {self.texto}"


class Narrador:
    def __init__(self, resultado: Resultado, semilla: int | None = None, faltas: float = 0.2):
        self.r = resultado
        self.rng = random.Random(semilla)
        self.prob_falta = faltas  # fracción de faltas comunes que se narran

    def _elige(self, opciones: list[str], **valores) -> str:
        return self.rng.choice(opciones).format(**valores)

    def _marcador(self, marcador) -> str:
        l, v = self.r.equipos
        return f"{l} {marcador[0]}-{marcador[1]} {v}"

    def _jugada(self, ev: Evento, resultado: str, tir: str, por: str) -> str:
        d = ev.datos
        jugada = d.get("jugada", "rebote")
        asis = d.get("asistente") or "un compañero"
        if jugada in ("centro", "centro_cabeza", "contragolpe", "pared", "pase_filtrado") and not d.get("asistente"):
            jugada = "rebote"
        eq_tiro = ev.equipo if resultado != "atajada" else 1 - ev.equipo
        valores = dict(tir=tir, asis=asis, por=por or "el arquero", rival=self.r.equipos[1 - eq_tiro])

        clave = resultado
        if d.get("penal"):
            clave = f"{resultado}_penal" if f"{resultado}_penal" in FINAL else resultado
        elif resultado == "gol" and jugada == "centro_cabeza":
            clave = "gol_cabeza"
        preparacion, final = self._elige(PREPARACION[jugada], **valores), self._elige(FINAL[clave], **valores)
        if preparacion.endswith(("!", ".")) and final.startswith("…"):
            # "¡Zapatazo desde lejos!… pero" se lee mal: se corta la frase y se empieza otra
            final = final.lstrip("… ")
            final = final[0].upper() + final[1:] if not final.startswith("¡") else "¡" + final[1].upper() + final[2:]
            return f"{preparacion} {final}"
        return preparacion + final

    def _contexto_gol(self, ev: Evento) -> str:
        eq, (g0, g1) = ev.equipo, ev.datos["marcador"]
        propios, rivales = (g0, g1) if eq == 0 else (g1, g0)
        equipo = self.r.equipos[eq]
        partes = []
        if ev.datos.get("golazo"):
            partes.append(self._elige(CONTEXTO_GOL["golazo"]))
        if ev.tiempo == 2 and ev.minuto >= 88:
            partes.append(self._elige(CONTEXTO_GOL["tarde"]))
        if g0 + g1 == 1:
            situacion = "primero"
        elif propios == rivales:
            situacion = "empate"
        elif propios == rivales + 1:
            situacion = "ventaja"
        elif propios > rivales:
            situacion = "amplia"
        else:
            situacion = "descuento"
        partes.append(self._elige(CONTEXTO_GOL[situacion], equipo=equipo))
        goles = ev.datos.get("goles_jugador", 1)
        if goles == 2:
            partes.append(self._elige(CONTEXTO_GOL["doblete"], tir=ev.jugador))
        elif goles == 3:
            partes.append(self._elige(CONTEXTO_GOL["triplete"], tir=ev.jugador))
        partes.append(f"**{self._marcador(ev.datos['marcador'])}**")
        return " ".join(partes)

    def _linea(self, ev: Evento) -> Linea | None:
        m = ev.minuto_texto
        equipo = self.r.equipos[ev.equipo] if ev.equipo >= 0 else ""
        d = ev.datos

        lado = (f" (Pateó {LADO[d['lado']]}; el arquero se tiró {LADO[d['adivina']]}.)"
                if d.get("lado") in LADO and d.get("adivina") in LADO else "")
        if ev.tipo == "gol":
            texto = self._jugada(ev, "gol", ev.jugador, d.get("portero", ""))
            return Linea(m, f"{texto}{lado} {self._contexto_gol(ev)}", "gol")
        if ev.tipo == "atajada":
            return Linea(m, self._jugada(ev, "atajada", d.get("tirador", ""), ev.jugador) + lado, "atajada")
        if ev.tipo in ("desviado", "palo"):
            texto = self._jugada(ev, ev.tipo, ev.jugador, "")
            if d.get("corner"):
                texto += f" Córner para {equipo}."
            return Linea(m, texto, ev.tipo)
        if ev.tipo == "falta":
            if self.rng.random() > self.prob_falta:
                return None
            return Linea(m, self._elige(SIMPLES["falta"], jug=ev.jugador, equipo=equipo), "falta")
        if ev.tipo == "roja":
            clave = "roja_directa" if d.get("directa") else "roja_doble"
            return Linea(m, self._elige(SIMPLES[clave], jug=ev.jugador, equipo=equipo), "roja")
        if ev.tipo == "cambio":
            if d.get("motivo") == "roja":
                return None
            clave = {"lesion": "cambio_lesion", "decision": "cambio_decision",
                     "tras_roja": "cambio_tras_roja"}.get(d.get("motivo"), "cambio_tactico")
            return Linea(m, self._elige(SIMPLES[clave], jug=ev.jugador, sale=d.get("sale", ""), equipo=equipo), "cambio")
        if ev.tipo == "tactica":
            return Linea(m, TACTICA.get(d.get("tactica"), "").format(equipo=equipo), "tactica")
        if ev.tipo == "perdida":
            clave = "perdida_gambeta" if d.get("como") == "gambeta" else "perdida_pase"
            return Linea(m, self._elige(SIMPLES[clave], jug=ev.jugador, otro=d.get("otro", "")), "perdida")
        if ev.tipo == "adicion":
            n = d["minutos"]
            return Linea(m, self._elige(SIMPLES["adicion"], min_add=f"{n} minuto{'s' if n != 1 else ''}", n="n" if n != 1 else ""), "adicion")
        if ev.tipo in SIMPLES:
            return Linea(m, self._elige(SIMPLES[ev.tipo], jug=ev.jugador, equipo=equipo, dias=d.get("dias", "")), ev.tipo)
        return None

    def _relleno_entre(self, previo: Evento, ev: Evento) -> Linea | None:
        """A veces, un comentario de ambiente en los huecos largos sin jugadas."""
        if previo.tiempo != ev.tiempo or ev.minuto - previo.minuto < 7 or self.rng.random() > 0.55:
            return None
        minuto = self.rng.randint(previo.minuto + 2, ev.minuto - 2)
        pos = [max(e["posesion"], 1) for e in self.r.estadisticas]
        eq = self.rng.choices([0, 1], weights=pos)[0]
        texto = self._elige(RELLENO, equipo=self.r.equipos[eq])
        return Linea(f"{minuto}'", texto, "relleno", minuto, ev.tiempo, eq)

    def tramo(self, desde: int = 0, hasta: int | None = None) -> list[Linea]:
        """Narra los eventos [desde:hasta]. Permite narrar el partido por partes (en vivo)."""
        l, v = self.r.equipos
        lineas: list[Linea] = []
        previo = self.r.eventos[desde - 1] if desde > 0 else None
        for ev in self.r.eventos[desde:hasta]:
            if previo is not None and ev.tipo not in ("descanso", "final", "adicion"):
                extra = self._relleno_entre(previo, ev)
                if extra:
                    lineas.append(extra)
            previo = ev
            marcador = list(ev.datos.get("marcador", (0, 0)))
            if ev.tipo == "inicio":
                tipo = "Liga rankeada" if self.r.tipo == "liga" else "Amistoso"
                lineas.append(Linea("", f"🏟️ **{l} 🆚 {v}** · {tipo}\n⏳ ¡Rueda la pelota!", "inicio", 0, 1))
                continue
            if ev.tipo == "descanso":
                lineas.append(Linea("", f"⏸️ **Descanso:** {self._marcador(marcador)}", "descanso", ev.minuto, 1,
                                    extra={"marcador": marcador}))
                continue
            if ev.tipo == "final":
                lineas.append(Linea("", f"🔔 **¡Final del partido!** {self._marcador(marcador)}", "final", ev.minuto, 2,
                                    extra={"marcador": marcador}))
                lineas.append(Linea("", self.resumen(), "resumen", ev.minuto, 2))
                continue
            linea = self._linea(ev)
            if linea:
                linea.min, linea.tiempo, linea.equipo = ev.minuto, ev.tiempo, ev.equipo
                linea.extra = {"marcador": marcador, "jugador": ev.jugador}
                # datos para animar la jugada en la cancha
                for k in ("sale", "asistente", "tirador", "penal", "lado", "adivina", "otro", "como", "tactica", "corner", "jugada"):
                    if ev.datos.get(k) not in (None, "", False):
                        linea.extra[k] = ev.datos[k]
                lineas.append(linea)
        return lineas

    def narrar(self) -> list[Linea]:
        return self.tramo(0)

    def resumen(self) -> str:
        r = self.r
        e0, e1 = r.estadisticas
        g = r.ganador
        cabecera = f"🤝 Empate {r.goles[0]}-{r.goles[1]}" if g < 0 else f"✅ Gana **{r.equipos[g]}** {max(r.goles)}-{min(r.goles)}"
        filas = [
            cabecera,
            f"📊 Posesión {e0['posesion']}% - {e1['posesion']}% · Tiros {e0['tiros']} ({e0['a_puerta']}) - {e1['tiros']} ({e1['a_puerta']}) · Faltas {e0['faltas']} - {e1['faltas']}",
        ]
        goleadores = [ev for ev in r.eventos if ev.tipo == "gol"]
        for eq in (0, 1):
            goles = [f"{ev.jugador} {ev.minuto_texto}{' (p)' if ev.datos.get('penal') else ''}" for ev in goleadores if ev.equipo == eq]
            if goles:
                filas.append(f"⚽ {r.equipos[eq]}: {', '.join(goles)}")
        if r.mvp[1]:
            filas.append(f"🏆 Jugador del partido: **{r.mvp[1]}** ({r.equipos[r.mvp[0]]}) · nota {r.mvp[2]}")
        for les in r.lesiones:
            filas.append(f"🚑 {les['jugador']} ({r.equipos[les['equipo']]}) fuera {les['dias']} día{'s' if les['dias'] != 1 else ''}")
        rojas = [t for t in r.tarjetas if t["tipo"] == "roja"]
        for t in rojas:
            filas.append(f"🟥 {t['jugador']} ({r.equipos[t['equipo']]}) suspendido")
        return "\n".join(filas)


def narrar(resultado: Resultado, semilla: int | None = None) -> list[Linea]:
    return Narrador(resultado, semilla).narrar()
