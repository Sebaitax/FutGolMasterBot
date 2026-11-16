// Estado del partido que se ve en pantalla (marcador, reloj, tácticas, relato, indicadores).
// Es un objeto con suscriptores: los componentes de Preact se vuelven a dibujar cuando cambia.
import {useEffect, useState} from '../vendor/preact-htm.js';

export function crearEstado(inicial) {
  let valor = {...inicial};
  const subs = new Set();
  return {
    get: () => valor,
    set(cambios) {
      valor = {...valor, ...(typeof cambios === 'function' ? cambios(valor) : cambios)};
      subs.forEach(f => f(valor));
    },
    suscribir(f) { subs.add(f); return () => subs.delete(f); },
  };
}

// hook: el componente se vuelve a dibujar con cada cambio del estado
export function usarEstado(estado) {
  const [v, setV] = useState(estado.get());
  useEffect(() => estado.suscribir(setV), [estado]);
  return v;
}

// minuto "absoluto" (el 45+2 del primer tiempo cuenta como 45; el segundo tiempo parte en 46)
export const absoluto = (t, m) => t === 1 ? Math.min(m, 45) : Math.max(m, 46);
export const clave = (t, m) => t * 1000 + m;
