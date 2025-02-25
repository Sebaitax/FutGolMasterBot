# 🎮⚽ **FutGolMasterBot**  
### 🤖 Bot de Discord - Colección de Cartas de Fútbol & Partidos Simulados  

---

## 📌 **Descripción**  
**FutGolMasterBot** es un bot de Discord que simula un sistema de **colección de cartas de jugadores de fútbol**, inspirado en **FIFA Ultimate Team**. También incluye una plataforma web donde los jugadores pueden **gestionar cartas, armar plantillas y disputar partidos amistosos y rankeados**.  

📌 **Tecnologías:**  
🔹 **Base de datos:** MongoDB  
🔹 **Plataformas:** Discord + Plataforma Web  

---

## 🚀 **Características Principales**  

### 🃏 **Sistema de Cartas**  
Cada carta representa a un jugador de fútbol con los siguientes atributos:  

✅ **Nombre del jugador**  
✅ **Tipo de carta:** Bronze 🟤 | Plata ⚪ | Oro 🟡  
✅ **Estadísticas:**  
   - ⚡ **Velocidad**  
   - 🎯 **Disparo**  
   - 🎩 **Pase**  
   - 🏃‍♂️ **Dribbling**  
   - 🛡️ **Defensa**  
   - 💪 **Físico**  
   - ⭐ **Overall**  
✅ **Otros atributos:**  
   - 💰 **Precio de venta rápida**  
   - 🏆 **Equipo y nacionalidad**  
   - 🖼️ **Imagen personalizada de la carta**  

---

### 🎒 **Inventario de Usuarios**  
Cada usuario puede poseer múltiples cartas y administrarlas en su inventario.  

📌 **Datos de cada carta en el inventario:**  
- 🔢 **ID** (Referencia a la colección de cartas)  
- 📈 **Nivel de mejora** (Cada carta puede mejorarse)  
- 🚑 **Estado**: Disponible, Lesionado, Suspendido  
- ⏳ **Duración de la lesión** (en días)  
- 🟨 **Tarjetas acumuladas** (Amistosos no acumulan amarillas, pero sí rojas y lesiones)  
- 📋 **Plantillas en las que está incluida**  

---

### ⚽ **Sistema de Partidos**  
FutGolMasterBot permite disputar dos tipos de partidos:  

🏆 **Amistosos**  
🔹 No afectan la acumulación de amarillas  
🔹 Las rojas y lesiones sí influyen  

🏅 **Liga Rankeda**  
🔹 Se aplican reglas de tarjetas amarillas, rojas y lesiones  
🔹 Partidos narrados en tiempo real en Discord con jugadas simuladas 🎙️  
🔹 **Duración simulada**: ⏱️ 3 minutos  

---

### 📋 **Plantillas y Formaciones**  
Cada usuario puede crear hasta **5 plantillas personalizadas**, seleccionando:  

- 🏟️ **Nombre de la plantilla**  
- 🏃‍♂️ **Jugadores seleccionados**  
- 📌 **Formación táctica:** 4-4-2, 3-5-2, etc.  
- 🏟️ **Estadio asignado**  

---

## 🎯 **Objetivos del Proyecto**  
✅ Crear una experiencia **interactiva y competitiva** en Discord  
✅ Fomentar la **estrategia en la gestión de equipos y partidos**  
✅ Desarrollar un sistema **escalable y dinámico** con MongoDB  

---

## 📜 **Tecnologías Utilizadas**  
- 🛠️ **Backend:** Python  
- 📡 **Base de Datos:** MongoDB  
- 🤖 **Plataforma:** Discord Bot + Web App  

---

## 🔥 **¡Colecciona cartas, arma tu equipo y domina el campo con FutGolMasterBot!** 🎮⚽  