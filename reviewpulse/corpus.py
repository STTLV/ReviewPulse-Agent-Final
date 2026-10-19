"""Generador de reseñas sintéticas en español para hoteles.

El corpus se construye a partir de frases plantilla por tema y polaridad.
Cada pool de frases se divide en dos: las frases "de entrenamiento" (75 %) y
las frases "no vistas" (25 %) que solo aparecen en el conjunto de evaluación.
Así la medida de exactitud no se calcula sobre frases que el modelo memorizó.

Polaridades: positiva, negativa, neutra.
Temas: limpieza, servicio, ubicacion, precio.
"""
from __future__ import annotations

import random
import unicodedata

TEMAS = ["limpieza", "servicio", "ubicacion", "precio"]
POLARIDADES = ["positiva", "negativa", "neutra"]

FRASES = {
    "limpieza": {
        "positiva": [
            "La habitación estaba impecable y olía a limpio.",
            "Las sábanas y las toallas siempre estaban limpias.",
            "El baño brillaba, se nota que lo asean a diario.",
            "Todo muy aseado, cero polvo en los muebles.",
            "Nos cambiaron las toallas todos los días sin pedirlo.",
            "La piscina y las zonas comunes se mantienen muy limpias.",
            "Ni un pelo en el baño, la limpieza es de diez.",
            "El cuarto estaba pulcro desde que llegamos.",
            "La camarera dejaba la habitación ordenadita cada mañana.",
            "Excelente aseo, se siente higiénico y fresco.",
            "Colchón y almohadas limpios, sin manchas.",
            "Muy pendientes del aseo de los pasillos y el lobby.",
        ],
        "negativa": [
            "La habitación estaba sucia y olía a humedad.",
            "Encontramos pelos en la ducha y manchas en las sábanas.",
            "El baño tenía hongos y el desagüe olía feo.",
            "Había cucarachas en el cuarto, un asco.",
            "Nunca vinieron a asear la habitación en tres días.",
            "Las toallas estaban percudidas y con mal olor.",
            "Polvo por todos lados y basura debajo de la cama.",
            "El aire acondicionado soltaba un olor a moho terrible.",
            "Las sábanas tenían manchas amarillas, muy desagradable.",
            "La piscina estaba turbia y con hojas.",
            "El piso pegajoso, como si nunca lo trapearan.",
            "Pedimos aseo varias veces y nadie apareció.",
        ],
        "neutra": [
            "La limpieza estaba normal, ni bien ni mal.",
            "El aseo cumple con lo básico.",
            "La habitación estaba aceptablemente limpia.",
            "La limpieza fue la esperada para un hotel de esta categoría.",
            "El baño estaba limpio aunque algo desgastado.",
            "El aseo es correcto, sin nada que destacar.",
            "Limpiaban el cuarto día de por medio.",
            "La limpieza de las zonas comunes es regular.",
            "El aseo fue el de siempre, sin sorpresas.",
            "La habitación estaba presentable, nada más.",
            "Limpio en general, aunque se notan los años.",
            "El aseo es promedio para el precio.",
        ],
    },
    "servicio": {
        "positiva": [
            "El personal fue muy amable y atento en todo momento.",
            "La recepcionista nos ayudó con todo, súper querida.",
            "Excelente atención, resolvieron cada solicitud rapidísimo.",
            "Los meseros del restaurante son muy serviciales.",
            "Nos recibieron con una bebida de bienvenida, detalle bonito.",
            "El check-in fue ágil y el trato muy cordial.",
            "El conserje nos recomendó planes buenísimos en la ciudad.",
            "El equipo del hotel siempre estuvo dispuesto a colaborar.",
            "Nos atendieron con mucha calidez, nos sentimos en casa.",
            "Respondieron enseguida cuando pedimos una almohada extra.",
            "El servicio a la habitación llegó rápido y caliente.",
            "Un trato de primera por parte de todo el personal.",
        ],
        "negativa": [
            "El personal fue grosero y poco servicial.",
            "Esperamos dos horas para el check-in sin explicación.",
            "En recepción nos ignoraron y nadie resolvió el problema.",
            "El servicio a la habitación nunca llegó.",
            "Los empleados respondían de mala gana.",
            "Llamamos varias veces a recepción y nadie contestó.",
            "Nos cobraron mal y el gerente no quiso atendernos.",
            "El mesero se demoró una eternidad y trajo el pedido equivocado.",
            "Pésima atención, nos trataron como si estorbáramos.",
            "Perdieron nuestra reserva y no ofrecieron solución.",
            "Nadie nos ayudó con las maletas y fueron muy secos.",
            "El check-out fue un caos, nos hicieron esperar demasiado.",
        ],
        "neutra": [
            "La atención fue correcta, sin más.",
            "El personal cumple con su trabajo.",
            "El servicio fue el estándar.",
            "En recepción fueron educados pero distantes.",
            "El check-in tomó el tiempo normal.",
            "El servicio del restaurante es aceptable.",
            "Atendieron lo que pedimos, nada especial.",
            "El trato fue neutral, ni cálido ni frío.",
            "Los empleados hacen su trabajo y ya.",
            "La atención es como la de cualquier hotel.",
            "El personal fue educado, sin mayor interacción.",
            "El servicio estuvo dentro de lo esperado.",
        ],
    },
    "ubicacion": {
        "positiva": [
            "La ubicación es perfecta, a dos cuadras de la playa.",
            "Queda cerca del centro histórico, todo se hace caminando.",
            "Excelente ubicación, rodeado de restaurantes y tiendas.",
            "Está a diez minutos del aeropuerto, muy práctico.",
            "La zona es segura y tranquila para caminar de noche.",
            "Ubicado en el mejor sector de la ciudad.",
            "La vista al mar desde la habitación es espectacular.",
            "Muy bien ubicado, cerca de la ciudad amurallada.",
            "Hay transporte público justo al frente del hotel.",
            "Queda en una zona muy bonita y con mucha vida.",
            "Ubicación estratégica para conocer todo.",
            "Estás a pasos de los mejores sitios turísticos.",
        ],
        "negativa": [
            "La ubicación es pésima, lejos de todo.",
            "La zona se siente insegura en la noche.",
            "Queda en un sector muy ruidoso, imposible dormir.",
            "Hay que tomar taxi para cualquier cosa, muy lejos.",
            "Los alrededores son feos y descuidados.",
            "El hotel está al lado de una discoteca, ruido toda la noche.",
            "Queda lejísimos de la playa, contrario a lo que anuncian.",
            "Difícil de llegar, ni los taxistas sabían dónde era.",
            "La calle es oscura y da miedo caminar.",
            "Está junto a una avenida con tráfico pesado y pitos todo el día.",
            "Muy mal ubicado, nada cerca para comer.",
            "La ubicación no corresponde con la que muestran en las fotos.",
        ],
        "neutra": [
            "La ubicación es aceptable.",
            "Queda en una zona normal, ni muy cerca ni muy lejos.",
            "La ubicación está bien para lo que necesitábamos.",
            "Está a unos veinte minutos del centro.",
            "La zona es residencial y tranquila, sin mucho alrededor.",
            "La ubicación es la que se ve en el mapa.",
            "Queda en un sector común de la ciudad.",
            "Se llega fácil, aunque no está en el centro.",
            "La ubicación es intermedia entre la playa y el centro.",
            "El barrio es normal, con algunas tiendas.",
            "Toca moverse un poco para llegar a los sitios turísticos.",
            "La zona no tiene mucho, pero tampoco es mala.",
        ],
    },
    "precio": {
        "positiva": [
            "Excelente relación calidad precio.",
            "Muy económico para todo lo que ofrece.",
            "Pagamos poco y recibimos mucho, súper recomendado.",
            "El precio es justo y el desayuno estaba incluido.",
            "Tarifas muy buenas comparadas con otros hoteles de la zona.",
            "Vale cada peso que pagamos.",
            "Conseguimos una promoción buenísima.",
            "Barato y cumplidor, ideal para viajar con presupuesto.",
            "Precio razonable sin cobros escondidos.",
            "Por ese valor no se consigue nada mejor.",
            "Muy buena tarifa para temporada alta.",
            "El paquete con todo incluido salió muy bien de precio.",
        ],
        "negativa": [
            "Demasiado caro para lo que ofrece.",
            "Nos cobraron cargos ocultos al salir.",
            "El precio no vale la pena, es un robo.",
            "Carísimo y el desayuno no estaba incluido.",
            "Pagamos una fortuna por una habitación pequeña.",
            "Cobran hasta el parqueadero y el wifi, abusivo.",
            "La tarifa subió el doble sin aviso.",
            "Por ese precio esperábamos mucho más.",
            "Los precios del minibar y el restaurante son exagerados.",
            "Nos cobraron una noche de más y no la devolvieron.",
            "Relación calidad precio muy mala.",
            "Es un hotel sobrevalorado y costoso.",
        ],
        "neutra": [
            "El precio es el normal del mercado.",
            "La tarifa está acorde con la categoría.",
            "Ni caro ni barato.",
            "El precio fue el que vimos en la página.",
            "Pagamos lo esperado para la temporada.",
            "El valor está dentro del promedio de la zona.",
            "El precio es razonable, sin más.",
            "Cobran lo justo por lo que es.",
            "La tarifa es la de cualquier hotel parecido.",
            "Lo que costó fue lo que esperábamos.",
            "El valor por noche es el promedio.",
            "No es barato pero tampoco caro.",
        ],
    },
}

# Ironía y sarcasmo: el texto suena positivo pero la reseña es negativa.
IRONIA = {
    "limpieza": [
        "Qué maravilla encontrar pelos ajenos de regalo en la almohada.",
        "Genial el aroma a humedad, se ve que lo cultivan con cariño.",
        "Muy original la colección de cucarachas del baño.",
    ],
    "servicio": [
        "Qué eficiencia, solo dos horas para darnos la llave.",
        "Encantadora la recepcionista que ni levantó la mirada.",
        "Excelente servicio a la habitación, lástima que nunca llegó.",
    ],
    "ubicacion": [
        "Perfecto si te encanta dormir con reguetón a todo volumen.",
        "Ideal para quienes aman caminar cuarenta minutos a la playa.",
        "Hermosa vista a la pared del edificio vecino.",
    ],
    "precio": [
        "Baratísimo, solo nos cobraron hasta el aire que respiramos.",
        "Qué ganga pagar eso por un cuarto del tamaño de un clóset.",
        "Una tarifa increíble, increíblemente alta.",
    ],
}

APERTURAS = [
    "Fuimos en familia el fin de semana.",
    "Estuve por trabajo tres noches.",
    "Llegamos un viernes en la tarde.",
    "Viajé con mi pareja por nuestro aniversario.",
    "Nos quedamos cinco días en temporada.",
    "Fue nuestra primera vez en este hotel.",
    "Vine con unos amigos de paseo.",
    "",
    "",
    "",
]

CIERRES = {
    "positiva": ["Volvería sin pensarlo.", "Muy recomendado.", "Gracias por todo.", "Cinco estrellas.", ""],
    "negativa": ["No vuelvo.", "No lo recomiendo.", "Qué decepción.", "Muy mala experiencia.", ""],
    "neutra": ["Estuvo bien.", "Nada del otro mundo.", "Cumple.", "", ""],
}

OTROS_IDIOMAS = [
    "The room was clean and the staff very friendly.",
    "Terrible location, very noisy at night.",
    "Great value for money, we loved the breakfast.",
    "O quarto estava sujo e o atendimento foi péssimo.",
    "Hotel muito bem localizado, perto da praia.",
    "Staff was rude and check-in took forever.",
    "Le personnel était très aimable et la chambre propre.",
]

ENTRADAS_INVALIDAS = ["", "   ", "😀😀😀👍", "<div><br></div>", "....", "null", "&nbsp;"]


def _particion(frases: list[str], conjunto: str, rng: random.Random | None = None) -> list[str]:
    """Separa frases de entrenamiento (3 de cada 4) y no vistas (1 de cada 4).

    "mezcla" (la usa el simulador) toma frases no vistas la mitad de las veces y
    vistas la otra mitad, para que el error del flujo se parezca al medido en M1.
    """
    if conjunto == "mezcla":
        conjunto = "evaluacion" if (rng or random).random() < 0.5 else "entrenamiento"
    if conjunto == "todas":
        return frases
    if conjunto == "entrenamiento":
        return [f for i, f in enumerate(frases) if i % 4 != 3]
    return [f for i, f in enumerate(frases) if i % 4 == 3]


def _quitar_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _ruido(texto: str, rng: random.Random) -> str:
    """Introduce ruido realista: minúsculas, sin tildes, errores de tipeo, emojis."""
    if rng.random() < 0.25:
        texto = texto.lower()
    if rng.random() < 0.20:
        texto = _quitar_tildes(texto)
    if rng.random() < 0.10 and len(texto) > 10:
        i = rng.randrange(1, len(texto) - 2)
        texto = texto[:i] + texto[i + 1] + texto[i] + texto[i + 2:]
    if rng.random() < 0.10:
        texto += rng.choice([" 😊", " 👎", "!!", " 🙄", " 👌"])
    return texto


def generar_resena(rng: random.Random, tema: str, polaridad: str, conjunto: str = "todas",
                   prob_ironia: float = 0.0, ruido: bool = True) -> dict:
    """Genera una reseña con su etiqueta verdadera (tema principal y polaridad)."""
    es_ironia = polaridad == "negativa" and rng.random() < prob_ironia
    partes = [rng.choice(APERTURAS)]
    if es_ironia:
        partes.append(rng.choice(IRONIA[tema]))
    secundaria = rng.random() < 0.30
    if not es_ironia:
        # El tema principal es el que más frases tiene: con mención secundaria lleva dos
        pool = _particion(FRASES[tema][polaridad], conjunto, rng)
        partes.extend(rng.sample(pool, k=min(len(pool), 2 if secundaria else rng.choice([1, 1, 2]))))
    # Mención secundaria de otro tema, siempre más débil (neutra o misma polaridad)
    if secundaria:
        otro = rng.choice([t for t in TEMAS if t != tema])
        pol2 = polaridad if rng.random() < 0.5 else "neutra"
        partes.append(rng.choice(_particion(FRASES[otro][pol2], conjunto, rng)))
    partes.append(rng.choice(CIERRES[polaridad]))
    texto = " ".join(p for p in partes if p)
    if ruido:
        texto = _ruido(texto, rng)
    return {"texto": texto, "tema": tema, "polaridad": polaridad, "ironia": es_ironia}


def calificacion_para(rng: random.Random, polaridad: str) -> int:
    """Calificación numérica de 1 a 5 correlacionada (con ruido) con la polaridad."""
    if rng.random() < 0.08:
        return rng.randint(1, 5)
    return {"positiva": rng.choice([4, 5, 5]), "negativa": rng.choice([1, 1, 2]),
            "neutra": rng.choice([3, 3, 2, 4])}[polaridad]


def construir_corpus(n: int, semilla: int, conjunto: str, prob_ironia: float = 0.0) -> list[dict]:
    """Corpus balanceado por tema; polaridad 45 % positiva, 30 % negativa, 25 % neutra."""
    rng = random.Random(semilla)
    corpus = []
    for _ in range(n):
        tema = rng.choice(TEMAS)
        polaridad = rng.choices(POLARIDADES, weights=[0.45, 0.30, 0.25])[0]
        corpus.append(generar_resena(rng, tema, polaridad, conjunto, prob_ironia))
    return corpus
