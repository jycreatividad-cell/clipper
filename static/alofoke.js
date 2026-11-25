// Biblioteca de hooks y copys para clips de La Casa de Alofoke.
// *palabra* = resaltada en color. tpl = plantilla PRO que mejor le queda.
// Edita o agrega frases aquí sin tocar el resto de la app.
window.ALOFOKE = {
  hashtags: {
    base: '#LaCasaDeAlofoke3 #LaCasaDeAlofoke #Alofoke #RD #RepublicaDominicana #Dominicanos',
    tiktok: '#fyp #parati #viral #tiktokrd',
    instagram: '#reels #reelsviral #explorar #viralrd',
    facebook: '#viral #videosvirales',
    whatsapp: '',
  },
  categorias: [
    {id: 'pelea', nombre: 'Pelea / Discusión', emoji: '🔥', tpl: 't:polemica',
      hooks: [
        'SE ARMÓ EL *LÍO* EN LA CASA DE ALOFOKE 😱',
        'SE DIJERON DE *TODO* EN VIVO 🔥',
        'NADIE SE ESPERABA ESTA *DISCUSIÓN* 😳',
        'ESTO SE SALIÓ DE *CONTROL*',
        'SE PRENDIÓ LA *CASA* 🔥',
        '¿QUIÉN TIENE LA *RAZÓN*? 👇',
        'LA PELEA QUE TIENE A TODO RD *HABLANDO*',
        'SE LE SALIÓ EL *DOMINICANO* 😂🔥',
        'ESTO ESTÁ *DURO* 😳',
      ],
      copys: [
        '🔥 Se calentó la cosa en La Casa de Alofoke 3 😱 ¿Quién tiene la razón? Te leo 👇',
        'Esto se salió de control en vivo 😳🔥 ¿De qué lado tú estás? 👇',
      ]},
    {id: 'romance', nombre: 'Romance / Novela', emoji: '💘', tpl: 't:revelacion',
      hooks: [
        'AQUÍ HAY ALGO MÁS QUE *AMISTAD* 👀',
        'LA PAREJA QUE NADIE *VIO VENIR* 💘',
        '¿AMOR REAL O *ESTRATEGIA*? 🤔',
        'LOS CELOS SE *NOTARON* EN VIVO 😳',
        'ESTA MIRADA LO DICE *TODO* 👀',
        'SE ESTÁ FORMANDO LA *NOVELA* EN LA CASA 💘',
      ],
      copys: [
        '👀 Aquí hay algo más que amistad… ¿Tú los shippeas o no? 💘👇',
        '¿Amor real o pura estrategia en La Casa de Alofoke? 🤔 Comenta 👇',
      ]},
    {id: 'nominacion', nombre: 'Nominación / Eliminación', emoji: '🗳️', tpl: 't:alerta',
      hooks: [
        'ÚLTIMA HORA: ASÍ QUEDÓ LA *NOMINACIÓN*',
        'NADIE ESPERABA ESTA *ELIMINACIÓN* 😱',
        '¿QUIÉN SE VA *ESTA SEMANA*? 👇',
        'LA DECISIÓN QUE CAMBIÓ *TODO* EN LA CASA',
        'LOS VOTOS *SORPRENDIERON* A TODOS',
      ],
      copys: [
        '🚨 Así quedó todo en La Casa de Alofoke 3 😱 ¿Quién crees que se va? 👇',
        'Nadie esperaba esta decisión 😳 ¿Fue justo o no? Te leo 👇',
      ]},
    {id: 'chisme', nombre: 'Confesión / Chisme', emoji: '🤫', tpl: 't:verdad',
      hooks: [
        'CONFESÓ LO QUE *NADIE SABÍA* 🤫',
        'SE LE ESCAPÓ EN *VIVO* 😳',
        'ESTO NO LO DIJO *DELANTE DE TODOS* 👀',
        'EL CHISME QUE TIENE A LA CASA *ENCENDIDA*',
        'POR FIN DIJO LA *VERDAD*',
        '¡DIQUE NO ERA *NADA*! 😂',
      ],
      copys: [
        '🤫 Se le escapó en vivo y ahora todo el mundo habla de esto 👀 ¿Qué opinas? 👇',
        'El chisme del día en La Casa de Alofoke 3 ☕👀',
      ]},
    {id: 'risa', nombre: 'Risa / Gracioso', emoji: '😂', tpl: 't:humor',
      hooks: [
        'ME MORÍ DE LA *RISA* CON ESTO 😂',
        'SOLO EN LA CASA DE ALOFOKE *PASA ESTO*',
        'EL MOMENTO MÁS *GRACIOSO* DEL DÍA 😂',
        'NO PUEDO PARAR DE *VERLO* 🤣',
        'EN RD NO HAY UN DÍA *ABURRIDO* 😂',
        'ESTO ES *TIGUERAJE* DEL BUENO 😂',
      ],
      copys: [
        '😂😂 Solo en La Casa de Alofoke pasa esto. Etiqueta a alguien que tiene que verlo 👇',
        'No puedo parar de verlo 🤣 ¿Cuántas veces lo viste tú?',
      ]},
    {id: 'alofoke', nombre: 'Reacción de Alofoke', emoji: '🎙️', tpl: 't:noticias',
      hooks: [
        'LA REACCIÓN DE *ALOFOKE* LO DICE TODO 😳',
        'ALOFOKE NO SE *AGUANTÓ* Y DIJO ESTO',
        'ALOFOKE PUSO ORDEN *EN LA CASA* 🔥',
        'MIREN CÓMO REACCIONÓ *ALOFOKE* 👀',
      ],
      copys: [
        '🎙️ La reacción de Alofoke lo dice todo 😳 ¿Estás de acuerdo? 👇',
        'Alofoke no se aguantó 🔥 Mira lo que dijo 👀',
      ]},
    {id: 'estrategia', nombre: 'Estrategia / Traición', emoji: '🐍', tpl: 't:impacto',
      hooks: [
        'LA TRAICIÓN QUE NADIE *VIO VENIR* 🐍',
        'SE ROMPIÓ LA *ALIANZA* EN VIVO',
        '¿ESTÁ JUGANDO *SUCIO*? 🤔',
        'ESTA JUGADA CAMBIA *EL JUEGO*',
        'LE VIRÓ LA *ESPALDA* 😳',
      ],
      copys: [
        '🐍 Nadie vio venir esta jugada en La Casa de Alofoke 3 😳 ¿Estrategia o traición? 👇',
        'Se rompió la alianza en vivo 😱 ¿Quién tiene la culpa? 👇',
      ]},
    {id: 'fiesta', nombre: 'Fiesta / Retos', emoji: '🎉', tpl: 't:viral',
      hooks: [
        'LA FIESTA SE PUSO *BUENA* 🎉',
        'EL RETO QUE TERMINÓ EN *CAOS* 😂',
        'BAILANDO ASÍ SE HIZO *VIRAL* 💃',
        'ESTE MOMENTO SE ESTÁ HACIENDO *VIRAL* 🔥',
      ],
      copys: [
        '🎉 La fiesta se puso buena en La Casa de Alofoke 3 💃🔥',
        'El reto que terminó en caos 😂 ¿Quién lo hizo mejor? 👇',
      ]},
    {id: 'emotivo', nombre: 'Emotivo', emoji: '😢', tpl: 't:reflexion',
      hooks: [
        'EL MOMENTO MÁS *EMOTIVO* DE LA CASA 😢',
        'NADIE PUDO AGUANTAR LAS *LÁGRIMAS*',
        'ESTO TE VA A TOCAR EL *CORAZÓN* ❤️',
        'ASÍ SE VIVIÓ ESTE *MOMENTO*',
      ],
      copys: [
        '😢❤️ El momento más emotivo de La Casa de Alofoke 3. ¿Te tocó a ti también?',
        'Nadie pudo aguantar las lágrimas 😢 Mira hasta el final ❤️',
      ]},
    {id: 'gancho', nombre: 'Gancho / Mira hasta el final', emoji: '👀', tpl: 't:curiosidad',
      hooks: [
        'ESPERA EL *FINAL* 👀',
        'LO QUE NO VISTE DEL *DIRECTO* 👀',
        'MIRA LO QUE PASÓ *ANOCHE* EN LA CASA',
        'ESTO PASÓ *HACE UNOS MINUTOS* 🚨',
        'NADIE ESPERABA *ESTA RESPUESTA*',
      ],
      copys: [
        '👀 Espera el final… Lo que pasó hoy en La Casa de Alofoke 3 🔥',
        'Esto pasó hace unos minutos en el directo 🚨 ¿Lo viste en vivo? 👇',
      ]},
  ],
};
