document.addEventListener('DOMContentLoaded', () => {
  let ws = null;
  let reconnectTimer = null;
  let currentState = 'IDLE';
  let activeCameraStream = null;
  let speechRecognizer = null;
  let isRebelMode = false;

  // Elementos DOM
  const body = document.body;
  const navTabs = document.querySelectorAll('.nav-tab');
  const connText = document.getElementById('connText');
  const connStatus = document.getElementById('connStatus');

  // Vista 1: Cara
  const faceTriggerArea = document.getElementById('faceTriggerArea');
  const faceWrapper = faceTriggerArea;
  const eyeLeft = document.getElementById('eyeLeft');
  const eyeRight = document.getElementById('eyeRight');
  const eyebrowLeft = document.getElementById('eyebrowLeft');
  const eyebrowRight = document.getElementById('eyebrowRight');
  const mouthMesh = document.getElementById('mouthMesh');
  const mouthCavity = document.getElementById('mouthCavity');
  const faceSpeechText = document.getElementById('faceSpeechText');
  const btnFaceMic = document.getElementById('btnFaceMic');
  const btnToggleCamera = document.getElementById('btnToggleCamera');
  const cameraVisor = document.getElementById('cameraVisor');
  const cameraVideo = document.getElementById('cameraVideo');
  const cameraCanvas = document.getElementById('cameraCanvas');
  const btnCloseCamera = document.getElementById('btnCloseCamera');
  const btnAnalyzeCamera = document.getElementById('btnAnalyzeCamera');

  // Vista 2: Control & Orbe
  const statusBadge = document.getElementById('statusBadge');
  const statusDetail = document.getElementById('statusDetail');
  const orbIcon = document.getElementById('orbIcon');
  const coreOrb = document.getElementById('coreOrb');
  const feedScroll = document.getElementById('feedScroll');
  const feedEmpty = document.getElementById('feedEmpty');
  const historyCount = document.getElementById('historyCount');
  const commandForm = document.getElementById('commandForm');
  const cmdInput = document.getElementById('cmdInput');
  const btnPushToTalk = document.getElementById('btnPushToTalk');
  const btnTestVoice = document.getElementById('btnTestVoice');
  const btnStopVoice = document.getElementById('btnStopVoice');
  const btnOpenSettings = document.getElementById('btnOpenSettings');
  const btnCloseModal = document.getElementById('btnCloseModal');
  const modalBackdrop = document.getElementById('modalBackdrop');
  const btnSaveKey = document.getElementById('btnSaveKey');
  const apiKeyInput = document.getElementById('apiKeyInput');
  const keyStatusMsg = document.getElementById('keyStatusMsg');
  const ring1 = document.querySelector('.ring-1');
  const ring2 = document.querySelector('.ring-2');

  // Vista 3: Telemetría
  const telemCpuTotal = document.getElementById('telemCpuTotal');
  const barCpuTotal = document.getElementById('barCpuTotal');
  const telemCpuFreq = document.getElementById('telemCpuFreq');
  const telemCpuCores = document.getElementById('telemCpuCores');
  const coresGrid = document.getElementById('coresGrid');
  const telemRamPercent = document.getElementById('telemRamPercent');
  const barRam = document.getElementById('barRam');
  const telemRamUsed = document.getElementById('telemRamUsed');
  const telemRamFree = document.getElementById('telemRamFree');
  const telemRamTotal = document.getElementById('telemRamTotal');
  const disksList = document.getElementById('disksList');
  const telemNetRecv = document.getElementById('telemNetRecv');
  const telemNetSent = document.getElementById('telemNetSent');
  const btnTelemMinimize = document.getElementById('btnTelemMinimize');
  const btnTelemLock = document.getElementById('btnTelemLock');
  const btnTelemScreenshot = document.getElementById('btnTelemScreenshot');

  let totalEvents = 0;
  let currentAssistantMode = 'normal';

  function updateActiveMode(mode) {
    currentAssistantMode = mode || 'normal';
    isRebelMode = (currentAssistantMode === 'rebel');

    body.classList.remove('mode-rebel', 'mode-kids', 'mode-tertulia');
    if (currentAssistantMode === 'rebel') {
      body.classList.add('mode-rebel');
    } else if (currentAssistantMode === 'kids') {
      body.classList.add('mode-kids');
    } else if (currentAssistantMode === 'tertulia') {
      body.classList.add('mode-tertulia');
    }

    document.querySelectorAll('.mode-pill').forEach(pill => {
      if (pill.dataset.mode === currentAssistantMode) {
        pill.classList.add('active');
      } else {
        pill.classList.remove('active');
      }
    });
  }

  function updateSpeakerBadge(speakerType, pitchHz) {
    const badge = document.getElementById('speakerBadge');
    const nameSpan = document.getElementById('speakerName');
    const iconSpan = document.getElementById('speakerIcon');
    if (!badge || !nameSpan || !iconSpan) return;

    badge.classList.remove('detected-hombre', 'detected-mujer', 'detected-nino');

    if (speakerType === 'hombre') {
      badge.classList.add('detected-hombre');
      iconSpan.textContent = '👨';
      nameSpan.textContent = `Hombre ${pitchHz ? Math.round(pitchHz) + 'Hz' : ''}`;
    } else if (speakerType === 'mujer') {
      badge.classList.add('detected-mujer');
      iconSpan.textContent = '👩';
      nameSpan.textContent = `Mujer ${pitchHz ? Math.round(pitchHz) + 'Hz' : ''}`;
    } else if (speakerType === 'nino') {
      badge.classList.add('detected-nino');
      iconSpan.textContent = '🧒';
      nameSpan.textContent = `Niño ${pitchHz ? Math.round(pitchHz) + 'Hz' : ''}`;
    } else {
      iconSpan.textContent = '🎙️';
      nameSpan.textContent = 'Voz: Auto';
    }
  }

  function initModeBar() {
    document.querySelectorAll('.mode-pill').forEach(pill => {
      pill.addEventListener('click', (e) => {
        e.stopPropagation();
        const mode = pill.dataset.mode;
        updateActiveMode(mode);
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'set_mode', mode: mode }));
        } else {
          fetch('/api/mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
          }).catch(() => {});
        }
      });
    });
  }

  // ============================================================
  // GESTIÓN DE VISTAS (PANTALLA 1, 2 Y 3)
  // ============================================================
  function switchView(viewName) {
    const valid = ['face', 'orb', 'telemetry'];
    const target = valid.includes(viewName) ? viewName : 'face';

    body.classList.remove('active-view-face', 'active-view-orb', 'active-view-telemetry');
    body.classList.add(`active-view-${target}`);

    navTabs.forEach(tab => {
      if (tab.getAttribute('data-view') === target) {
        tab.classList.add('active');
      } else {
        tab.classList.remove('active');
      }
    });

    if (target !== 'face') {
      body.classList.remove('ui-hidden');
      if (uiHideTimer) {
        clearTimeout(uiHideTimer);
        uiHideTimer = null;
      }
    } else {
      resetUiHideTimer();
    }

    if (target === 'telemetry' && typeof fetchTelemetry === 'function') {
      fetchTelemetry();
    }
  }

  // ============================================================
  // AUTO-OCULTAMIENTO DE INTERFAZ EN MODO CARA (PANTALLA LIMPIA J2)
  // ============================================================
  let uiHideTimer = null;
  const UI_AUTO_HIDE_MS = 3500; // 3.5 segundos de inactividad

  function showUI() {
    body.classList.remove('ui-hidden');
    resetUiHideTimer();
  }

  function hideUI() {
    // Solo auto-ocultar si estamos en la vista de la CARA
    if (body.classList.contains('active-view-face')) {
      body.classList.add('ui-hidden');
    }
  }

  function resetUiHideTimer() {
    if (uiHideTimer) {
      clearTimeout(uiHideTimer);
      uiHideTimer = null;
    }
    // Solo programar auto-ocultamiento si estamos viendo la cara
    if (body.classList.contains('active-view-face')) {
      uiHideTimer = setTimeout(hideUI, UI_AUTO_HIDE_MS);
    } else {
      body.classList.remove('ui-hidden');
    }
  }

  function initCleanScreenController() {
    // Detectar cualquier interacción: toques en pantalla, movimientos, clics o teclas
    const interactionEvents = ['touchstart', 'touchmove', 'mousedown', 'mousemove', 'click', 'keydown'];
    interactionEvents.forEach(evt => {
      window.addEventListener(evt, () => {
        if (body.classList.contains('ui-hidden')) {
          showUI();
        } else {
          resetUiHideTimer();
        }
      }, { passive: true });
    });

    // Iniciar temporizador de reposo
    resetUiHideTimer();
  }

  navTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const view = tab.getAttribute('data-view');
      if (view) {
        switchView(view);
        sendWs({ type: 'switch_view', view: view });
      }
    });
  });

  // Botón de Pantalla Completa
  const btnFullscreen = document.getElementById('btnFullscreen');
  if (btnFullscreen) {
    btnFullscreen.addEventListener('click', () => {
      if (!document.fullscreenElement) {
        const el = document.documentElement;
        const rfs = el.requestFullscreen || el.webkitRequestFullScreen || el.mozRequestFullScreen;
        if (rfs) rfs.call(el).catch(() => {});
      } else {
        const efs = document.exitFullscreen || document.webkitExitFullscreen || document.mozCancelFullScreen;
        if (efs) efs.call(document).catch(() => {});
      }
    });
  }

  // Wake Lock para evitar que la pantalla se apague desde el navegador
  let wakeLock = null;
  async function requestWakeLock() {
    if ('wakeLock' in navigator) {
      try {
        wakeLock = await navigator.wakeLock.request('screen');
      } catch (e) {}
    }
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      requestWakeLock();
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        connectWebSocket();
      }
      if (micAudioCtx && micAudioCtx.state === 'suspended') {
        micAudioCtx.resume().catch(() => {});
      }
      if (isHandsFree && (!micWs || micWs.readyState !== WebSocket.OPEN)) {
        startSilentAudioStreaming();
      }
    }
  });

  window.addEventListener('focus', () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connectWebSocket();
    }
    if (micAudioCtx && micAudioCtx.state === 'suspended') {
      micAudioCtx.resume().catch(() => {});
    }
    if (isHandsFree && (!micWs || micWs.readyState !== WebSocket.OPEN)) {
      startSilentAudioStreaming();
    }
  });

  document.addEventListener('click', () => {
    if (micAudioCtx && micAudioCtx.state === 'suspended') {
      micAudioCtx.resume().catch(() => {});
    }
    if (isHandsFree && (!micWs || micWs.readyState !== WebSocket.OPEN)) {
      startSilentAudioStreaming();
    }
  }, { passive: true });

  // ============================================================
  // CONEXIÓN WEBSOCKET
  // ============================================================
  function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      connText.textContent = 'ON';
      connStatus.querySelector('.dot').style.backgroundColor = 'var(--neon-green)';
      connStatus.querySelector('.dot').style.boxShadow = '0 0 8px var(--neon-green)';
      if (reconnectTimer) {
        clearInterval(reconnectTimer);
        reconnectTimer = null;
      }
      if (isHandsFree) {
        startSilentAudioStreaming();
      }
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        handleWsMessage(payload);
      } catch (e) {
        console.error('Error parseando WS:', e);
      }
    };

    ws.onclose = () => {
      connText.textContent = 'OFF';
      connStatus.querySelector('.dot').style.backgroundColor = 'var(--neon-red)';
      connStatus.querySelector('.dot').style.boxShadow = '0 0 8px var(--neon-red)';
      if (reconnectTimer) {
        clearInterval(reconnectTimer);
        reconnectTimer = null;
      }
      reconnectTimer = setInterval(connectWebSocket, 2000);
    };

    ws.onerror = () => ws.close();
  }

  function handleWsMessage(msg) {
    if (typeof resetIdleTimer === 'function') {
      if (msg.type === 'wake_pulse' || msg.type === 'trigger_listen') {
        resetIdleTimer(true);
      } else if (msg.type === 'user_speech') {
        const txt = (msg.text || '').toLowerCase();
        const isRest = /mate|descans|dormi|mimir|siesta|pausa|amargo/.test(txt);
        if (!isRest && !['mate', 'drowsy', 'sleeping'].includes(currentInactivityStage)) {
          resetIdleTimer(true);
        }
      }
    }

    switch (msg.type) {
      case 'set_stage':
        if (typeof setInactivityStage === 'function') {
          setInactivityStage(msg.stage, true);
        }
        break;

      case 'init_snapshot':
        const initMode = msg.data.current_mode || (msg.data.is_rebel_mode ? 'rebel' : 'normal');
        updateActiveMode(initMode);
        if (msg.data.last_speaker) {
          updateSpeakerBadge(msg.data.last_speaker.type, msg.data.last_speaker.pitch);
        }
        if (initMode === 'rebel') {
          updateRebelPatience(100);
        }
        if (msg.data.is_hands_free !== undefined) {
          setHandsFree(msg.data.is_hands_free, false);
        }
        updateState(msg.data.state, msg.data.detail);
        if (msg.data.inactivity_stage && msg.data.inactivity_stage !== 'idle') {
          if (typeof setInactivityStage === 'function') {
            setInactivityStage(msg.data.inactivity_stage, false);
          }
          if (msg.data.idle_seconds !== undefined) {
            idleSeconds = msg.data.idle_seconds;
          }
        } else {
          if (typeof setInactivityStage === 'function') {
            setInactivityStage('idle', false);
          }
          idleSeconds = msg.data.idle_seconds || 0;
        }
        if (msg.data.history && msg.data.history.length > 0) {
          msg.data.history.forEach(appendHistoryItem);
        }
        break;

      case 'state_change':
        updateState(msg.state, msg.detail);
        break;

      case 'switch_view':
        switchView(msg.view);
        break;

      case 'user_speech':
      case 'assistant_speech':
      case 'tool_execution':
        appendHistoryItem(msg);
        if (msg.type === 'assistant_speech') {
          // Solo actualizar texto en pantalla — la boca se mueve con speech_playing
          updateFaceSpeech(msg.text);
        }
        break;

      // ← Audio COMENZÓ a sonar
      case 'speech_playing':
        startVisemeSpeech(msg.text || '');
        break;

      // ← Audio TERMINÓ → detener animación de boca inmediatamente
      case 'speech_stopped':
        resetMouth();
        stopBrowserAudio();
        break;

      case 'play_audio':
        playAudioBase64(msg.audio_base64, msg.text);
        break;

      case 'speech_level':
        handleSpeechLevelLipSync(msg.level);
        break;

      case 'audio_level':
        if (currentState !== 'SPEAKING') {
          handleLipSyncAndWaves(msg.level);
        }
        break;

      case 'flip_camera':
        flipCamera(msg.mode);
        break;

      case 'capture_j2_photo':
        captureJ2PhotoForTelegram(msg.request_id, msg.facing_mode);
        break;

      case 'wake_pulse':
        triggerWakePulse();
        break;

      case 'rebel_patience':
        updateRebelPatience(msg.patience);
        break;

      case 'rebel_mode':
        isRebelMode = !!msg.enabled;
        updateActiveMode(isRebelMode ? 'rebel' : 'normal');
        if (isRebelMode) {
          updateState(currentState, 'MODO REBELDE 🤬');
          updateRebelPatience(msg.patience !== undefined ? msg.patience : 100);
          playSFX('rebel_on');
          triggerRebelRecoil(false);
        } else {
          updateState(currentState, 'En espera de activación');
          playSFX('rebel_off');
        }
        break;

      case 'mode_change':
        updateActiveMode(msg.mode);
        if (msg.mode === 'rebel') {
          updateState(currentState, 'MODO REBELDE 🤬');
          playSFX('rebel_on');
          triggerRebelRecoil(false);
        } else if (msg.mode === 'kids') {
          updateState(currentState, 'MODO PIBES 👶 (ATP)');
          playSFX('rebel_off');
        } else {
          updateState(currentState, 'MODO COMPINCHE 🧉');
          playSFX('rebel_off');
        }
        break;

      case 'speaker_detected':
        updateSpeakerBadge(msg.speaker, msg.pitch);
        break;

      case 'hands_free_changed':
        setHandsFree(!!msg.enabled, false);
        break;

      case 'image_generating':
        handleImageGenerating(msg);
        break;

      case 'image_generated':
        handleImageGenerated(msg);
        break;

      default:
        break;
    }
  }

  // ============================================================
  // REPRODUCTOR DE VOZ EN EL NAVEGADOR (HUD / Celular / PC)
  // Permite escuchar a Titán directamente por los parlantes del dispositivo
  // donde esté abierta la pantalla (Samsung J2 o navegador de la PC).
  // ============================================================
  let audioQueue = [];
  let isPlayingAudio = false;
  let currentAudioEl = null;
  // Por defecto, la voz de Titán sale por el Servidor DDR3.
  // En las demás pantallas (navegadores/celular) permanece silenciada por defecto,
  // salvo que el usuario la active manualmente tocando el botón de sonido (guardado como 'true' en localStorage).
  let isBrowserAudioMuted = localStorage.getItem('titan_voice_output_enabled') !== 'true';

  function updateMuteButtonUI() {
    const icon1 = document.getElementById('muteAudioIcon');
    const icon2 = document.getElementById('btnFloatMuteAudio');
    const btn1 = document.getElementById('btnMuteAudio');
    const symbol = isBrowserAudioMuted ? '🔇' : '🔊';
    if (icon1) icon1.textContent = symbol;
    if (icon2) icon2.textContent = symbol;
    if (btn1) {
      btn1.style.color = isBrowserAudioMuted ? 'var(--neon-red)' : 'var(--neon-green)';
      btn1.style.borderColor = isBrowserAudioMuted ? 'rgba(255, 51, 102, 0.5)' : 'rgba(0, 255, 136, 0.5)';
      btn1.title = isBrowserAudioMuted
        ? 'Voz silenciada en esta pantalla (sale por Servidor Titán DDR3). Clic para escucharla acá.'
        : 'Voz activada en esta pantalla. Clic para silenciar.';
    }
  }

  function toggleBrowserAudioMute() {
    isBrowserAudioMuted = !isBrowserAudioMuted;
    localStorage.setItem('titan_voice_output_enabled', isBrowserAudioMuted ? 'false' : 'true');
    updateMuteButtonUI();
    if (isBrowserAudioMuted) {
      stopBrowserAudio();
      if (typeof showToast === 'function') showToast('🔇 Voz silenciada en esta pantalla (sale por Servidor DDR3)', false);
    } else {
      if (typeof showToast === 'function') showToast('🔊 Voz activada en esta pantalla', true);
    }
  }

  function playAudioBase64(b64Data, text) {
    if (!b64Data) return;
    if (isBrowserAudioMuted) {
      if (text) updateFaceSpeech(text);
      return;
    }
    audioQueue.push({ b64: b64Data, text: text });
    processAudioQueue();
  }

  function stopBrowserAudio() {
    audioQueue = [];
    if (currentAudioEl) {
      try {
        currentAudioEl.pause();
        currentAudioEl.currentTime = 0;
        currentAudioEl = null;
      } catch (e) {}
    }
    isPlayingAudio = false;
  }

  function processAudioQueue() {
    if (isPlayingAudio || audioQueue.length === 0) return;
    const item = audioQueue.shift();
    isPlayingAudio = true;

    try {
      const audioUrl = "data:audio/mp3;base64," + item.b64;
      currentAudioEl = new Audio(audioUrl);

      currentAudioEl.onplay = () => {
        updateState('SPEAKING', 'Hablando...');
        if (item.text) updateFaceSpeech(item.text);
      };

      currentAudioEl.onended = () => {
        isPlayingAudio = false;
        currentAudioEl = null;
        if (audioQueue.length > 0) {
          processAudioQueue();
        }
      };

      currentAudioEl.onerror = () => {
        isPlayingAudio = false;
        currentAudioEl = null;
        if (audioQueue.length > 0) {
          processAudioQueue();
        }
      };

      const playPromise = currentAudioEl.play();
      if (playPromise !== undefined) {
        playPromise.catch(e => {
          console.warn("Autoplay en espera de interacción táctil/clic del usuario:", e);
          isPlayingAudio = false;
          currentAudioEl = null;
          if (audioQueue.length > 0) {
            processAudioQueue();
          }
        });
      }
    } catch (e) {
      console.error("Excepción reproduciendo audio en navegador:", e);
      isPlayingAudio = false;
      currentAudioEl = null;
    }
  }

  // ============================================================
  // SINTETIZADOR WEB AUDIO API PARA SFX NATIVOS (SIN ARCHIVOS EXTERNOS)
  // ============================================================
  let sfxAudioCtx = null;
  function getSfxAudioCtx() {
    if (!sfxAudioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        sfxAudioCtx = new AudioContextClass();
      }
    }
    if (sfxAudioCtx && sfxAudioCtx.state === 'suspended') {
      sfxAudioCtx.resume().catch(() => {});
    }
    return sfxAudioCtx;
  }

  function playSFX(name) {
    const ctx = getSfxAudioCtx();
    if (!ctx) return;
    try {
      const now = ctx.currentTime;
      if (name === 'rebel_on') {
        // Distorsión y acorde agresivo descendente (tono 340Hz -> 80Hz)
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(340, now);
        osc.frequency.exponentialRampToValueAtTime(80, now + 0.5);
        gain.gain.setValueAtTime(0.35, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.55);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.55);
      } else if (name === 'rebel_off') {
        // Campana zen relajante (acorde armónico 528Hz + 660Hz)
        [528, 660].forEach((freq) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = 'sine';
          osc.frequency.setValueAtTime(freq, now);
          gain.gain.setValueAtTime(0.18, now);
          gain.gain.exponentialRampToValueAtTime(0.001, now + 0.85);
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.start(now);
          osc.stop(now + 0.85);
        });
      } else if (name === 'slap') {
        // Bofetada / golpe seco (impacto percusivo + latigazo)
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(220, now);
        osc.frequency.exponentialRampToValueAtTime(45, now + 0.16);
        gain.gain.setValueAtTime(0.45, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.18);

        // Burst de ruido blanco para el impacto de cachetazo
        const bufferSize = Math.floor(ctx.sampleRate * 0.12);
        const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < bufferSize; i++) {
          data[i] = (Math.random() * 2 - 1) * Math.exp(-16 * (i / ctx.sampleRate));
        }
        const noise = ctx.createBufferSource();
        const noiseGain = ctx.createGain();
        noise.buffer = buffer;
        noiseGain.gain.setValueAtTime(0.4, now);
        noiseGain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
        noise.connect(noiseGain);
        noiseGain.connect(ctx.destination);
        noise.start(now);
      }
    } catch (e) {
      console.warn("SFX error:", e);
    }
  }

  function updateRebelPatience(patiencePct) {
    const patienceValEl = document.getElementById('patienceVal');
    const patienceBarEl = document.getElementById('patienceBar');
    const pct = Math.max(0, Math.min(100, patiencePct !== undefined ? patiencePct : 100));
    if (patienceValEl) patienceValEl.textContent = `${pct}%`;
    if (patienceBarEl) {
      patienceBarEl.style.width = `${pct}%`;
      if (pct <= 25) {
        patienceBarEl.style.background = 'linear-gradient(90deg, #990000, #ff0000)';
      } else if (pct <= 60) {
        patienceBarEl.style.background = 'linear-gradient(90deg, #ff0000, #ff4400)';
      } else {
        patienceBarEl.style.background = 'linear-gradient(90deg, #ff0000, #ff8800)';
      }
    }
  }

  function triggerRebelRecoil(withSlap = true) {
    const caraEl = document.getElementById('cara');
    if (caraEl) {
      caraEl.classList.remove('rebel-recoil');
      void caraEl.offsetWidth; // forzar reflow
      caraEl.classList.add('rebel-recoil');
      setTimeout(() => caraEl.classList.remove('rebel-recoil'), 400);
    }
    if (withSlap) {
      playSFX('slap');
    }
    const rebelShouts = [
      "¡No me toqués, forro!",
      "¡Sacá la mano de ahí, carajo!",
      "¿Qué tocás, pedazo de vago?",
      "¡No me toqués que no te conozco!",
      "¡Dejá de tocar la pantalla, tarado!"
    ];
    updateFaceSpeech(rebelShouts[Math.floor(Math.random() * rebelShouts.length)]);
  }

  function triggerFriendTap() {
    const caraEl = document.getElementById('cara');
    if (caraEl) {
      caraEl.classList.remove('friend-bounce');
      void caraEl.offsetWidth; // forzar reflow
      caraEl.classList.add('friend-bounce');
      setTimeout(() => caraEl.classList.remove('friend-bounce'), 450);
    }
    // Guiño compinche y sonrisa
    if (eyeRight) {
      eyeRight.classList.add('wink');
      setTimeout(() => eyeRight.classList.remove('wink'), 750);
    }
    if (mouthMesh) {
      mouthMesh.classList.add('smile');
      setTimeout(() => mouthMesh.classList.remove('smile'), 1600);
    }
    const friendPhrases = [
      "¡Qué hacés, fiera!",
      "¡Acá firme al pie del cañón, papá!",
      "Decime qué necesitás, máquina.",
      "Todo tranqui por acá, ¿en qué te doy una mano?",
      "¡Siempre listo para salir a ganar!"
    ];
    updateFaceSpeech(friendPhrases[Math.floor(Math.random() * friendPhrases.length)]);
  }

  function updateState(state, detail) {
    if (state !== 'IDLE' && typeof resetIdleTimer === 'function') {
      const isRestStage = ['mate', 'drowsy', 'sleeping'].includes(currentInactivityStage);
      if (!isRestStage) {
        resetIdleTimer(true);
      }
    }
    currentState = state;
    
    // Quitar estados anteriores de color
    body.classList.remove('state-idle', 'state-listening', 'state-processing', 'state-executing', 'state-speaking', 'state-error');
    
    const stateMap = {
      'IDLE': { cls: 'state-idle', badge: isRebelMode ? 'REBELDE' : 'EN ESPERA', icon: isRebelMode ? '🤬' : '🎙', brow: 0 },
      'LISTENING': { cls: 'state-listening', badge: isRebelMode ? 'QUÉ QUERÉS...' : 'ESCUCHANDO...', icon: isRebelMode ? '🖕' : '👂', brow: -6 },
      'PROCESSING': { cls: 'state-processing', badge: isRebelMode ? 'QUÉ BOLUDEZ...' : 'PENSANDO...', icon: '⚡', brow: -4 },
      'EXECUTING_TOOL': { cls: 'state-executing', badge: 'EJECUTANDO...', icon: '⚙️', brow: 0 },
      'SPEAKING': { cls: 'state-speaking', badge: isRebelMode ? 'BARDEANDO...' : 'HABLANDO...', icon: isRebelMode ? '🤬' : '🔊', brow: -2 },
      'ERROR': { cls: 'state-error', badge: 'ATENCIÓN', icon: '⚠️', brow: 4 }
    };

    const s = stateMap[state] || stateMap['IDLE'];
    body.classList.add(s.cls);
    statusBadge.textContent = s.badge;
    orbIcon.textContent = s.icon;
    if (detail) statusDetail.textContent = detail;

    // Ajustar expresión facial completa (ojos, cejas, boca y gestos)
    if (isRebelMode) {
      if (state === 'LISTENING') {
        // Gesto: Ceja irónica alzada (The Rock), ojo escéptico y boca torcida
        if (eyebrowLeft) eyebrowLeft.style.transform = 'translateY(-6px) rotate(-8deg)';
        if (eyebrowRight) eyebrowRight.style.transform = 'translateY(15px) rotate(-28deg)';
        if (eyeLeft) eyeLeft.style.transform = 'scale(1.06)';
        if (eyeRight) eyeRight.style.transform = 'scaleY(0.62)';
        if (mouthMesh) mouthMesh.style.transform = 'rotate(-5deg) translateY(2px)';
      } else if (state === 'PROCESSING') {
        // Gesto: Furia concentrada, cejas apretadas hacia abajo y ojos achinados
        if (eyebrowLeft) eyebrowLeft.style.transform = 'translateY(16px) rotate(28deg)';
        if (eyebrowRight) eyebrowRight.style.transform = 'translateY(16px) rotate(-28deg)';
        if (eyeLeft) eyeLeft.style.transform = 'scaleY(0.46) scaleX(0.9)';
        if (eyeRight) eyeRight.style.transform = 'scaleY(0.46) scaleX(0.9)';
        if (mouthMesh) mouthMesh.style.transform = 'rotate(-3deg) translateY(3px)';
      } else if (state === 'SPEAKING') {
        // Gesto: Bardeando con bronca
        if (eyebrowLeft) eyebrowLeft.style.transform = 'translateY(11px) rotate(22deg)';
        if (eyebrowRight) eyebrowRight.style.transform = 'translateY(11px) rotate(-22deg)';
        if (eyeLeft) eyeLeft.style.transform = 'scaleY(0.85)';
        if (eyeRight) eyeRight.style.transform = 'scaleY(0.85)';
        if (mouthMesh) mouthMesh.style.transform = 'none';
      } else {
        // IDLE: Mueca de desprecio y cejas enojadas
        if (eyebrowLeft) eyebrowLeft.style.transform = 'translateY(8px) rotate(20deg)';
        if (eyebrowRight) eyebrowRight.style.transform = 'translateY(8px) rotate(-20deg)';
        if (eyeLeft) eyeLeft.style.transform = 'scaleY(0.72)';
        if (eyeRight) eyeRight.style.transform = 'scaleY(0.72)';
        if (mouthMesh) mouthMesh.style.transform = 'rotate(-5deg) translateY(2px)';
      }
    } else {
      // Modo normal amigo de fierro: expresiones amables y vivas
      if (state === 'PROCESSING') {
        // Gesto de curiosidad pensativa
        if (eyebrowLeft) eyebrowLeft.style.transform = 'translateY(-8px) rotate(-8deg)';
        if (eyebrowRight) eyebrowRight.style.transform = 'translateY(2px) rotate(4deg)';
        if (eyeLeft) eyeLeft.style.transform = 'scale(1.06)';
        if (eyeRight) eyeRight.style.transform = 'scaleY(0.88)';
        if (mouthMesh) mouthMesh.style.transform = 'none';
      } else if (state === 'SPEAKING') {
        if (eyebrowLeft) eyebrowLeft.style.transform = 'translateY(-3px) rotate(2deg)';
        if (eyebrowRight) eyebrowRight.style.transform = 'translateY(-3px) rotate(-2deg)';
        if (eyeLeft) eyeLeft.style.transform = 'none';
        if (eyeRight) eyeRight.style.transform = 'none';
        if (mouthMesh) mouthMesh.style.transform = 'none';
      } else if (state === 'LISTENING') {
        if (eyebrowLeft) eyebrowLeft.style.transform = 'translateY(-6px) rotate(-4deg)';
        if (eyebrowRight) eyebrowRight.style.transform = 'translateY(-6px) rotate(4deg)';
        if (eyeLeft) eyeLeft.style.transform = 'none';
        if (eyeRight) eyeRight.style.transform = 'none';
        if (mouthMesh) mouthMesh.style.transform = 'none';
      } else {
        // IDLE: Limpiar transforms en línea para que corran las animaciones orgánicas de CSS y miradas
        if (currentInactivityStage === 'idle') {
          if (eyebrowLeft) eyebrowLeft.style.transform = '';
          if (eyebrowRight) eyebrowRight.style.transform = '';
          if (eyeLeft) eyeLeft.style.transform = '';
          if (eyeRight) eyeRight.style.transform = '';
          if (mouthMesh) mouthMesh.style.transform = '';
          if (typeof scheduleNextGlance === 'function') scheduleNextGlance();
        } else {
          clearFaceTransformsForStages();
        }
      }
    }

    // Control de articulación de la boca: SOLO se activa con speech_playing,
    // NO en el cambio de estado SPEAKING (la síntesis TTS todavía no está sonando)
    if (state !== 'SPEAKING') {
      resetMouth();
    }

    if (state === 'LISTENING' && detail && (detail.includes('seguí') || detail.includes('Te escucho'))) {
      if (faceWrapper) faceWrapper.classList.add('conversing');
      if (faceSpeechText) faceSpeechText.textContent = 'Te escucho... (seguí hablando o decí "chau")';
    } else {
      if (faceWrapper) faceWrapper.classList.remove('conversing');
    }
  }

  function updateFaceSpeech(text) {
    if (faceSpeechText) {
      faceSpeechText.textContent = text;
    }
  }

  function triggerWakePulse() {
    if (faceWrapper) {
      faceWrapper.classList.add('wake-pulse');
      setTimeout(() => {
        faceWrapper.classList.remove('wake-pulse');
      }, 1400);
    }
  }

  // ============================================================
  // SISTEMA DE INACTIVIDAD Y REPOSO EN 3 ETAPAS
  // 15 min (900s) -> Etapa 1: El Recreo con Mate y Pava
  // 30 min (1800s) -> Etapa 2: La Modorra (cabeceo y bostezo)
  // 45 min (2700s) -> Etapa 3: Modo Siesta Zzz
  // Despertar -> Sobresalto Cómico 3A (1.15s)
  // ============================================================
  let idleSeconds = 0;
  let currentInactivityStage = 'idle'; // 'idle' | 'mate' | 'drowsy' | 'sleeping'
  let isWakeStartleActive = false;
  let idleInterval = null;

  function clearFaceTransformsForStages() {
    if (eyebrowLeft) eyebrowLeft.style.transform = '';
    if (eyebrowRight) eyebrowRight.style.transform = '';
    if (eyeLeft) eyeLeft.style.transform = '';
    if (eyeRight) eyeRight.style.transform = '';
    if (mouthMesh) {
      mouthMesh.style.transform = '';
      if (typeof ALL_VISEMES !== 'undefined') {
        ALL_VISEMES.forEach(cls => mouthMesh.classList.remove(cls));
      }
    }
    const caraEl = document.getElementById('cara');
    if (caraEl) caraEl.style.transform = '';
  }

  function setInactivityStage(stage, manual = false) {
    if (isWakeStartleActive && stage !== 'wake') return;

    const validStages = ['idle', 'mate', 'drowsy', 'sleeping', 'wake'];
    const s = validStages.includes(stage) ? stage : 'idle';

    if (s === 'wake') {
      wakeUpWithStartle();
      return;
    }

    currentInactivityStage = s;
    body.classList.remove('stage-mate', 'stage-drowsy', 'stage-sleeping', 'stage-wake-startle');

    if (s === 'mate' || s === 'drowsy' || s === 'sleeping') {
      if (typeof switchView === 'function' && !body.classList.contains('active-view-face')) {
        switchView('face');
      }
    }

    if (s === 'mate') {
      if (manual) idleSeconds = 900;
      clearFaceTransformsForStages();
      body.classList.add('stage-mate');
    } else if (s === 'drowsy') {
      if (manual) idleSeconds = 1800;
      clearFaceTransformsForStages();
      body.classList.add('stage-drowsy');
    } else if (s === 'sleeping') {
      if (manual) idleSeconds = 2700;
      clearFaceTransformsForStages();
      body.classList.add('stage-sleeping');
    } else {
      // idle
      clearFaceTransformsForStages();
      scheduleNextGlance();
    }
  }

  function wakeUpWithStartle() {
    if (isWakeStartleActive) return;
    const wasResting = (currentInactivityStage !== 'idle');
    isWakeStartleActive = true;
    idleSeconds = 0;
    currentInactivityStage = 'idle';

    body.classList.remove('stage-mate', 'stage-drowsy', 'stage-sleeping');
    clearFaceTransformsForStages();

    if (wasResting) {
      body.classList.add('stage-wake-startle');
      triggerWakePulse();

      setTimeout(() => {
        body.classList.remove('stage-wake-startle');
        isWakeStartleActive = false;
        clearFaceTransformsForStages();
        scheduleNextGlance();
        scheduleNextBlink();
      }, 1150);
    } else {
      isWakeStartleActive = false;
      body.classList.remove('stage-wake-startle');
    }
  }

  function resetIdleTimer(triggerWake = true, sendToServer = false) {
    if (triggerWake && currentInactivityStage !== 'idle') {
      wakeUpWithStartle();
    }
    idleSeconds = 0;
    if (sendToServer && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'record_activity', trigger_wake: triggerWake }));
    }
  }

  function initInactivityTracker() {
    if (idleInterval) clearInterval(idleInterval);
    idleInterval = setInterval(() => {
      if (currentState === 'IDLE' && !isPlayingAudio && !isWakeStartleActive) {
        idleSeconds++;

        if (idleSeconds >= 2700) {
          if (currentInactivityStage !== 'sleeping') {
            setInactivityStage('sleeping');
          }
        } else if (idleSeconds >= 1800) {
          if (currentInactivityStage !== 'drowsy') {
            setInactivityStage('drowsy');
          }
        } else if (idleSeconds >= 900) {
          if (currentInactivityStage !== 'mate') {
            setInactivityStage('mate');
          }
        }
      }
    }, 1000);

    const userEvents = ['touchstart', 'mousedown', 'keydown'];
    userEvents.forEach(evt => {
      window.addEventListener(evt, () => {
        resetIdleTimer(true, true);
      }, { passive: true });
    });
  }

  // ============================================================
  // SISTEMA DE VIDA EN REPOSO Y ANIMACIÓN FACIAL ORGÁNICA
  // ============================================================

  // 1. Parpadeo orgánico: simple, doble parpadeo y guiños compinches
  function scheduleNextBlink() {
    const delay = Math.random() * 3200 + 2000; // Entre 2 y 5.2 segundos
    setTimeout(() => {
      if (currentInactivityStage !== 'idle' || isWakeStartleActive) {
        scheduleNextBlink();
        return;
      }
      if (eyeLeft && eyeRight) {
        const isWink = (!isRebelMode && currentState === 'IDLE' && Math.random() < 0.16);
        const isDouble = (currentState === 'IDLE' && !isWink && Math.random() < 0.35);

        if (isWink) {
          // Guiño cómplice con sonrisa
          eyeRight.classList.add('wink');
          if (mouthMesh) mouthMesh.classList.add('smile');
          setTimeout(() => {
            eyeRight.classList.remove('wink');
            if (mouthMesh) mouthMesh.classList.remove('smile');
            scheduleNextBlink();
          }, 450);
        } else if (isDouble) {
          // Doble parpadeo humano / orgánico
          eyeLeft.classList.add('blink');
          eyeRight.classList.add('blink');
          setTimeout(() => {
            eyeLeft.classList.remove('blink');
            eyeRight.classList.remove('blink');
            setTimeout(() => {
              eyeLeft.classList.add('blink');
              eyeRight.classList.add('blink');
              setTimeout(() => {
                eyeLeft.classList.remove('blink');
                eyeRight.classList.remove('blink');
                scheduleNextBlink();
              }, 110);
            }, 80);
          }, 110);
        } else {
          // Parpadeo simple normal
          eyeLeft.classList.add('blink');
          eyeRight.classList.add('blink');
          setTimeout(() => {
            eyeLeft.classList.remove('blink');
            eyeRight.classList.remove('blink');
            scheduleNextBlink();
          }, 130);
        }
      } else {
        scheduleNextBlink();
      }
    }, delay);
  }
  scheduleNextBlink();

  // 2. Sistema de miradas autónomas (Eye Glances & Micro-Saccades)
  let idleGlanceTimer = null;
  let mouseTrackingActive = false;
  let mouseIdleTimeout = null;

  function doAutonomousGlance() {
    if (currentState !== 'IDLE' || mouseTrackingActive || currentInactivityStage !== 'idle' || isWakeStartleActive) {
      scheduleNextGlance();
      return;
    }

    // Variaciones orgánicas de miradas en reposo
    const options = [
      { x: -5, y: 0, browL: 0, browR: 0, headRot: -1.2, duration: 2200 },
      { x: 5, y: 0, browL: 0, browR: 0, headRot: 1.2, duration: 2200 },
      { x: 0, y: -4, browL: -2, browR: -4, headRot: 0.8, duration: 2400 },
      { x: -4, y: 2, browL: 1, browR: -2, headRot: -0.6, duration: 1800 },
      { x: 4, y: 2, browL: -2, browR: 1, headRot: 0.6, duration: 1800 },
      { x: 0, y: 0, browL: -3, browR: 0, headRot: 0, duration: 1600 } // Leve arqueo de ceja
    ];

    const chosen = options[Math.floor(Math.random() * options.length)];
    applyGlance(chosen.x, chosen.y, chosen.browL, chosen.browR, chosen.headRot);

    setTimeout(() => {
      if (currentState === 'IDLE' && !mouseTrackingActive) {
        resetGlance();
      }
      scheduleNextGlance();
    }, chosen.duration);
  }

  function applyGlance(x, y, browL = 0, browR = 0, headRot = 0) {
    if (currentInactivityStage !== 'idle' || isWakeStartleActive) return;
    if (!eyeLeft || !eyeRight) return;
    const glanceTransform = `translate(${x}px, ${y}px)`;
    eyeLeft.style.transform = glanceTransform;
    eyeRight.style.transform = glanceTransform;

    if (eyebrowLeft && browL !== 0) {
      eyebrowLeft.style.transform = `translateY(${browL}px)`;
    }
    if (eyebrowRight && browR !== 0) {
      eyebrowRight.style.transform = `translateY(${browR}px)`;
    }
    const caraEl = document.getElementById('cara');
    if (caraEl && headRot !== 0) {
      caraEl.style.transform = `rotate(${headRot}deg)`;
    }
  }

  function resetGlance() {
    if (currentState !== 'IDLE' || currentInactivityStage !== 'idle' || isWakeStartleActive) return;
    if (eyeLeft) eyeLeft.style.transform = '';
    if (eyeRight) eyeRight.style.transform = '';
    if (eyebrowLeft) eyebrowLeft.style.transform = '';
    if (eyebrowRight) eyebrowRight.style.transform = '';
    const caraEl = document.getElementById('cara');
    if (caraEl) caraEl.style.transform = '';
  }

  function scheduleNextGlance() {
    clearTimeout(idleGlanceTimer);
    const delay = Math.random() * 3000 + 2500; // Entre 2.5s y 5.5s
    idleGlanceTimer = setTimeout(doAutonomousGlance, delay);
  }
  scheduleNextGlance();

  // 3. Seguimiento interactivo por cursor / dedo (Parallax reactivo)
  function initInteractiveTracking() {
    const faceArea = document.getElementById('faceTriggerArea');
    if (!faceArea) return;

    function handlePointerMove(e) {
      if (currentState !== 'IDLE' || currentInactivityStage !== 'idle' || isWakeStartleActive) return;
      const rect = faceArea.getBoundingClientRect();
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const clientY = e.touches ? e.touches[0].clientY : e.clientY;

      if (!clientX || !clientY) return;

      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;

      const deltaX = (clientX - centerX) / (rect.width / 2);
      const deltaY = (clientY - centerY) / (rect.height / 2);

      const eyeX = Math.max(-7, Math.min(7, deltaX * 7));
      const eyeY = Math.max(-5, Math.min(5, deltaY * 5));
      const headTilt = Math.max(-2, Math.min(2, deltaX * 2));

      mouseTrackingActive = true;
      applyGlance(eyeX, eyeY, 0, 0, headTilt);

      clearTimeout(mouseIdleTimeout);
      mouseIdleTimeout = setTimeout(() => {
        mouseTrackingActive = false;
        resetGlance();
      }, 1800);
    }

    faceArea.addEventListener('mousemove', handlePointerMove, { passive: true });
    faceArea.addEventListener('touchmove', handlePointerMove, { passive: true });
  }
  initInteractiveTracking();

  function handleLipSyncAndWaves(level) {
    // 1. Modulación de ondas del orbe
    if (ring1 && ring2) {
      const scale1 = 1 + (level * 0.4);
      const scale2 = 1 + (level * 0.8);
      ring1.style.transform = `scale(${scale1})`;
      ring2.style.transform = `scale(${scale2})`;
    }

    // 2. Gesto de cejas vibrando con furia al gritar en modo rebelde
    if (isRebelMode && currentState === 'SPEAKING') {
      const bounce = Math.min(8, level * 12);
      if (eyebrowLeft) eyebrowLeft.style.transform = `translateY(${11 - bounce}px) rotate(${22 + bounce * 0.4}deg)`;
      if (eyebrowRight) eyebrowRight.style.transform = `translateY(${11 - bounce}px) rotate(${-22 - bounce * 0.4}deg)`;
    }
  }

  // ============================================================
  // MOTOR DE VISEMAS Y ARTICULACIÓN FONÉTICA (SINCRONIZACIÓN POR AUDIO REAL)
  // ============================================================
  const ALL_VISEMES = ['viseme-open', 'viseme-round', 'viseme-closed', 'viseme-dental', 'viseme-rest'];
  let lastVisemeChangeTime = 0;
  let currentVisemeIdx = 0;

  function setMouthViseme(visemeClass) {
    if (!mouthMesh) return;
    ALL_VISEMES.forEach(cls => mouthMesh.classList.remove(cls));
    if (visemeClass) {
      mouthMesh.classList.add(visemeClass);
    }
  }

  function resetMouth() {
    if (mouthMesh) {
      ALL_VISEMES.forEach(cls => mouthMesh.classList.remove(cls));
      if (currentInactivityStage !== 'idle') {
        mouthMesh.style.transform = '';
        return;
      }
      mouthMesh.classList.add('viseme-rest');
      if (isRebelMode && currentState === 'IDLE') {
        mouthMesh.style.transform = 'rotate(-5deg) translateY(2px)';
      } else {
        mouthMesh.style.transform = 'none';
      }
    }
  }

  function handleSpeechLevelLipSync(level) {
    // 1. Si no está hablando o el volumen es silencio / pausa (< 0.05):
    // La boca se detiene y se cierra de inmediato en reposo natural
    if (currentState !== 'SPEAKING' || level <= 0.05) {
      if (mouthMesh) {
        ALL_VISEMES.forEach(cls => mouthMesh.classList.remove(cls));
        if (currentInactivityStage !== 'idle') {
          mouthMesh.style.transform = '';
          return;
        }
        mouthMesh.classList.add('viseme-rest');
        mouthMesh.style.transform = 'none';
      }
      return;
    }

    // 2. Modulación activa de fonemas y apertura según la velocidad y volumen de la voz
    if (mouthMesh) {
      const now = performance.now();
      // Cadencia natural de articulación fonética humana (~90ms entre sílabas)
      if (now - lastVisemeChangeTime > 90) {
        lastVisemeChangeTime = now;
        ALL_VISEMES.forEach(cls => mouthMesh.classList.remove(cls));

        let chosenViseme = 'viseme-dental';
        if (level > 0.45) {
          // Volumen alto / vocal abierta pronunciada (A, E)
          chosenViseme = 'viseme-open';
        } else if (level > 0.22) {
          // Volumen medio / vocal redondeada (O, U)
          chosenViseme = (currentVisemeIdx % 2 === 0) ? 'viseme-round' : 'viseme-open';
        } else {
          // Volumen suave / consonante o cierre (S, T, D, M, P)
          chosenViseme = (currentVisemeIdx % 2 === 0) ? 'viseme-dental' : 'viseme-closed';
        }
        currentVisemeIdx++;
        mouthMesh.classList.add(chosenViseme);
      }

      // Escalar apertura de la boca según la potencia instantánea de la voz
      const scale = Math.min(1.45, 0.75 + level * 0.95);
      mouthMesh.style.transform = `scaleY(${scale.toFixed(2)})`;
    }

    // 3. Reactividad de cejas y orbe con el volumen del habla
    handleLipSyncAndWaves(level);
  }

  function startVisemeSpeech(text) {
    if (text) {
      updateFaceSpeech(text);
    }
  }

  // ============================================================
  // MICRÓFONO DIRECTO DEL CELULAR (Web Speech API)
  // ============================================================
  function triggerMobileMic() {
    // Si el asistente está hablando, tocar cualquier botón interrumpe de inmediato:
    if (currentState === 'SPEAKING') {
      sendWs({ type: 'interrupt' });
      updateState('LISTENING', 'Te escucho...');
      updateFaceSpeech('Te escucho...');
      return;
    }

    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    // En celular, asegurarse de que el streaming continuo esté activo:
    if (isMobile && !isHandsFree) {
      setHandsFree(true);
    }

    updateState('LISTENING', '¡Te escucho! Decime...');
    updateFaceSpeech('¡Te escucho! Decime tu orden...');
    sendWs({ type: 'trigger_listen' });
  }

  // ============================================================
  // MODO MANOS LIBRES SILENCIOSO (Web Audio PCM Streamer)
  // Cero clics, cero beeps de Android, privacidad total en la sala.
  // ============================================================
  const btnHandsFree = document.getElementById('btnHandsFree');
  const handsFreeLabel = document.getElementById('handsFreeLabel');
  const navBtnHandsFree = document.getElementById('navBtnHandsFree');
  const navHandsFreeLabel = document.getElementById('navHandsFreeLabel');
  let isHandsFree = false;
  let micAudioCtx = null;
  let micStream = null;
  let micProcessor = null;
  let micWs = null;

  function downsampleTo16kHzPCM(float32Buffer, inputSampleRate) {
    const targetSampleRate = 16000;
    if (inputSampleRate === targetSampleRate) {
      const pcm16 = new Int16Array(float32Buffer.length);
      for (let i = 0; i < float32Buffer.length; i++) {
        const s = Math.max(-1, Math.min(1, float32Buffer[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      }
      return pcm16.buffer;
    }
    const ratio = inputSampleRate / targetSampleRate;
    const newLen = Math.round(float32Buffer.length / ratio);
    const pcm16 = new Int16Array(newLen);
    let offsetResult = 0;
    let offsetBuffer = 0;
    while (offsetResult < newLen) {
      const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
      let accum = 0, count = 0;
      for (let i = offsetBuffer; i < nextOffsetBuffer && i < float32Buffer.length; i++) {
        accum += float32Buffer[i];
        count++;
      }
      const sample = count ? accum / count : 0;
      const s = Math.max(-1, Math.min(1, sample));
      pcm16[offsetResult] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      offsetResult++;
      offsetBuffer = nextOffsetBuffer;
    }
    return pcm16.buffer;
  }

  function toggleHandsFree() {
    setHandsFree(!isHandsFree);
  }

  function setHandsFree(enabled, sendWs = true) {
    isHandsFree = !!enabled;
    try {
      localStorage.setItem('titan_hands_free', isHandsFree ? '1' : '0');
    } catch (e) {}

    const btnFloatHandsFree = document.getElementById('btnFloatHandsFree');
    if (btnFloatHandsFree) btnFloatHandsFree.classList.toggle('active', isHandsFree);

    if (isHandsFree) {
      if (btnHandsFree) btnHandsFree.classList.add('active');
      if (handsFreeLabel) handsFreeLabel.textContent = 'MANOS LIBRES';
      if (navBtnHandsFree) navBtnHandsFree.classList.add('active');
      if (navHandsFreeLabel) navHandsFreeLabel.textContent = 'MANOS LIBRES';

      const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
      if (isMobile) {
        updateFaceSpeech('¡Manos libres activo! Decí "Titán" cuando quieras.');
        startSilentAudioStreaming();
      } else {
        updateFaceSpeech('¡Manos libres activo! Titán te escucha continuamente.');
      }
    } else {
      if (btnHandsFree) btnHandsFree.classList.remove('active');
      if (handsFreeLabel) handsFreeLabel.textContent = 'PULSAR PARA HABLAR';
      if (navBtnHandsFree) navBtnHandsFree.classList.remove('active');
      if (navHandsFreeLabel) navHandsFreeLabel.textContent = 'PULSAR PARA HABLAR';
      updateFaceSpeech('Pulsar para hablar: tocá la pantalla o usá Ctrl+Espacio en la PC.');
      stopSilentAudioStreaming();
    }

    if (sendWs && ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'set_hands_free', enabled: isHandsFree }));
    }
  }

  function startSilentAudioStreaming() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      console.warn('getUserMedia no soportado');
      return;
    }

    if (!micWs || micWs.readyState !== WebSocket.OPEN) {
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      micWs = new WebSocket(`${protocol}//${location.host}/ws/mic`);
      micWs.binaryType = 'arraybuffer';
      micWs.onopen = () => {
        captureMicrophoneStream();
      };
      micWs.onclose = () => {
        micWs = null;
        if (isHandsFree) setTimeout(startSilentAudioStreaming, 2000);
      };
      micWs.onerror = () => {
        if (micWs) micWs.close();
      };
    } else {
      captureMicrophoneStream();
    }
  }

  async function captureMicrophoneStream() {
    if (micStream) {
      if (micAudioCtx && micAudioCtx.state === 'suspended') {
        micAudioCtx.resume().catch(() => {});
      }
      return;
    }

    let stream = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
    } catch (e1) {
      console.warn("Constraints avanzados no soportados, intentando audio básico:", e1);
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (e2) {
        console.error("Error accediendo a getUserMedia:", e2);
        if (!window.isSecureContext) {
          updateFaceSpeech('⚠️ Usá http://localhost:8000 para habilitar el micrófono.');
        } else if (e2.name === 'NotFoundError' || (e2.message && e2.message.toLowerCase().includes('not found'))) {
          updateFaceSpeech('ℹ️ En esta compu no hay micrófono conectado. Podés hablarle desde el celular.');
        } else if (e2.name === 'NotAllowedError' || e2.name === 'PermissionDeniedError') {
          updateFaceSpeech('⚠️ Tocá la pantalla para habilitar el micrófono.');
        } else if (e2.name === 'NotReadableError') {
          updateFaceSpeech('⚠️ Micrófono ocupado por otra app. Cerrá otras pestañas.');
        } else {
          updateFaceSpeech('⚠️ Error abriendo micrófono: ' + (e2.message || e2.name));
        }
        return;
      }
    }

    try {
      micStream = stream;
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      micAudioCtx = new AudioCtx();
      const inputRate = micAudioCtx.sampleRate;
      const source = micAudioCtx.createMediaStreamSource(stream);
      micProcessor = micAudioCtx.createScriptProcessor(4096, 1, 1);

      const muteGain = micAudioCtx.createGain();
      muteGain.gain.value = 0;

      if (micAudioCtx.state === 'suspended') {
        micAudioCtx.resume().catch(() => {});
      }

      micProcessor.onaudioprocess = (e) => {
        if (!isHandsFree) return;
        if (!micWs || micWs.readyState !== WebSocket.OPEN) return;

        const floatData = e.inputBuffer.getChannelData(0);
        const pcmBuffer = downsampleTo16kHzPCM(floatData, inputRate);
        micWs.send(pcmBuffer);
      };

      source.connect(micProcessor);
      micProcessor.connect(muteGain);
      muteGain.connect(micAudioCtx.destination);
      console.log('Transmisión de micrófono en vivo iniciada (AudioContext state:', micAudioCtx.state, ')');
    } catch (err) {
      console.error("Error configurando Web Audio:", err);
    }
  }

  // Asegurar activación del AudioContext ante cualquier toque del usuario
  function ensureAudioContext() {
    if (micAudioCtx && micAudioCtx.state === 'suspended') {
      micAudioCtx.resume();
    }
  }
  window.addEventListener('click', ensureAudioContext);
  window.addEventListener('touchstart', ensureAudioContext, { passive: true });

  window._titan = {
    get isHandsFree() { return isHandsFree; },
    get micWsState() { return micWs ? micWs.readyState : -1; },
    get audioState() { return micAudioCtx ? micAudioCtx.state : 'none'; },
    get inactivityStage() { return currentInactivityStage; },
    get idleSeconds() { return idleSeconds; },
    setInactivityStage,
    wakeUpWithStartle,
    setHandsFree,
    toggleHandsFree
  };

  function stopSilentAudioStreaming() {
    if (micStream) {
      micStream.getTracks().forEach(t => t.stop());
      micStream = null;
    }
    if (micAudioCtx) {
      try { micAudioCtx.close(); } catch (e) {}
      micAudioCtx = null;
    }
    if (micWs) {
      try { micWs.close(); } catch (e) {}
      micWs = null;
    }
  }

  if (btnHandsFree) btnHandsFree.addEventListener('click', toggleHandsFree);
  if (navBtnHandsFree) navBtnHandsFree.addEventListener('click', toggleHandsFree);

  if (btnFaceMic) btnFaceMic.addEventListener('click', triggerMobileMic);

  // ============================================================
  // CÁMARA: "LOS OJOS DEL ASISTENTE" (Frontal por defecto)
  // ============================================================
  const cameraFileInput = document.getElementById('cameraFileInput');
  const btnFlipCamera = document.getElementById('btnFlipCamera');
  const camIndicatorLabel = document.getElementById('camIndicatorLabel');

  // Cámara por defecto: 'user' (delantera/frontal), opcional 'environment' (trasera)
  let currentFacingMode = 'user';

  function updateCamIndicator() {
    if (camIndicatorLabel) {
      camIndicatorLabel.textContent = currentFacingMode === 'user' ? 'DELANTERA (FRONTAL)' : 'TRASERA (POSTERIOR)';
    }
    if (cameraFileInput) {
      cameraFileInput.setAttribute('capture', currentFacingMode === 'user' ? 'user' : 'environment');
    }
  }

  async function flipCamera(mode) {
    if (mode === 'user' || mode === 'environment') {
      currentFacingMode = mode;
    } else {
      currentFacingMode = currentFacingMode === 'user' ? 'environment' : 'user';
    }
    updateCamIndicator();

    // Si la cámara estaba activa, reiniciar el stream con la nueva cámara
    if (activeCameraStream) {
      stopCamera();
      await startCamera();
    }
  }

  if (btnFlipCamera) {
    btnFlipCamera.addEventListener('click', (e) => {
      e.stopPropagation();
      flipCamera();
    });
  }

  async function toggleCamera() {
    if (activeCameraStream) {
      stopCamera();
    } else {
      await startCamera();
    }
  }

  async function startCamera() {
    updateCamIndicator();

    // Función compatible con WebRTC moderno y WebViews antiguos de Android
    const requestMedia = (constraints) => {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        return navigator.mediaDevices.getUserMedia(constraints);
      }
      const legacyGetUserMedia = navigator.webkitGetUserMedia || navigator.getUserMedia || navigator.mozGetUserMedia;
      if (legacyGetUserMedia) {
        return new Promise((resolve, reject) => {
          legacyGetUserMedia.call(navigator, constraints, resolve, reject);
        });
      }
      return Promise.reject(new Error('WebRTC no disponible'));
    };

    try {
      // Intento 1: Cámara seleccionada (frontal por defecto)
      activeCameraStream = await requestMedia({
        video: { facingMode: { ideal: currentFacingMode } }
      });
      cameraVideo.srcObject = activeCameraStream;
      cameraVisor.classList.add('active');
    } catch (err1) {
      try {
        // Intento 2: Video con facingMode directo
        activeCameraStream = await requestMedia({ video: { facingMode: currentFacingMode } });
        cameraVideo.srcObject = activeCameraStream;
        cameraVisor.classList.add('active');
      } catch (err2) {
        try {
          // Intento 3: Video genérico
          activeCameraStream = await requestMedia({ video: true });
          cameraVideo.srcObject = activeCameraStream;
          cameraVisor.classList.add('active');
        } catch (err3) {
          console.warn('WebRTC no disponible, usando cámara nativa:', err3);
          triggerNativeCameraCapture();
        }
      }
    }
  }

  function triggerNativeCameraCapture() {
    if (cameraFileInput) {
      updateCamIndicator();
      cameraFileInput.value = '';
      cameraFileInput.click();
    }
  }

  // Manejar foto tomada con la cámara nativa de Android
  if (cameraFileInput) {
    cameraFileInput.addEventListener('change', (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;

      const reader = new FileReader();
      reader.onload = async (event) => {
        const b64Image = event.target.result;
        await sendImageToGemini(b64Image);
      };
      reader.readAsDataURL(file);
    });
  }

  function stopCamera() {
    if (activeCameraStream) {
      activeCameraStream.getTracks().forEach(t => t.stop());
      activeCameraStream = null;
    }
    cameraVisor.classList.remove('active');
  }

  if (btnToggleCamera) btnToggleCamera.addEventListener('click', toggleCamera);
  if (btnCloseCamera) btnCloseCamera.addEventListener('click', stopCamera);
  function captureLiveCameraFrameAndSend(question) {
    if (!activeCameraStream) return;
    cameraCanvas.width = cameraVideo.videoWidth || 640;
    cameraCanvas.height = cameraVideo.videoHeight || 480;
    const ctx = cameraCanvas.getContext('2d');
    ctx.drawImage(cameraVideo, 0, 0, cameraCanvas.width, cameraCanvas.height);
    const b64Image = cameraCanvas.toDataURL('image/jpeg', 0.85);
    sendImageToGemini(b64Image, question);
  }

  async function sendImageToGemini(b64Image, customQuestion) {
    const q = customQuestion || 'Che, fijate qué es esto que te muestro y decime brevemente';
    updateState('PROCESSING', 'Analizando con Gemini...');
    updateFaceSpeech('Dejame ver qué es eso...');

    try {
      const res = await fetch('/api/vision/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_base64: b64Image,
          question: q
        })
      });
      const data = await res.json();
      if (data.reply) {
        updateFaceSpeech(data.reply);
      }
    } catch (e) {
      console.error('Error enviando imagen:', e);
      updateFaceSpeech('Uy che, falló el envío de la foto.');
    }
  }

  async function captureJ2PhotoForTelegram(requestId, requestedFacing) {
    console.log('[Camera J2] Solicitud de captura remota:', requestId, requestedFacing);
    const targetFacing = requestedFacing || currentFacingMode || 'environment';

    try {
      const wasRunning = !!activeCameraStream;

      // Si no hay cámara activa o no coincide el facing, activarla
      if (!activeCameraStream || currentFacingMode !== targetFacing) {
        if (activeCameraStream) {
          stopCamera();
        }
        currentFacingMode = targetFacing;
        await startCamera();
      }

      // Esperar hasta que el video tenga dimensiones activas
      let ready = false;
      for (let i = 0; i < 25; i++) {
        if (cameraVideo && cameraVideo.videoWidth > 0 && cameraVideo.videoHeight > 0) {
          ready = true;
          break;
        }
        await new Promise(r => setTimeout(r, 120));
      }

      if (!ready || !cameraVideo || cameraVideo.videoWidth === 0) {
        throw new Error('No se pudo inicializar el video de la cámara en el J2.');
      }

      cameraCanvas.width = cameraVideo.videoWidth || 640;
      cameraCanvas.height = cameraVideo.videoHeight || 480;
      const ctx = cameraCanvas.getContext('2d');
      ctx.drawImage(cameraVideo, 0, 0, cameraCanvas.width, cameraCanvas.height);
      const b64Result = cameraCanvas.toDataURL('image/jpeg', 0.85);

      // Si antes no estaba corriendo la cámara, la detenemos para ahorrar batería
      if (!wasRunning) {
        stopCamera();
      }

      if (b64Result && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'j2_photo_result',
          request_id: requestId,
          status: 'success',
          image_base64: b64Result
        }));
        console.log('[Camera J2] Foto capturada y enviada con éxito para Telegram');
      } else {
        throw new Error('WebSocket no disponible para enviar foto.');
      }

    } catch (err) {
      console.error('[Camera J2] Fallo capturando foto remota:', err);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'j2_photo_result',
          request_id: requestId,
          status: 'error',
          error: err.message || String(err)
        }));
      }
    }
  }

  if (btnAnalyzeCamera) {
    btnAnalyzeCamera.addEventListener('click', () => {
      if (!activeCameraStream) {
        triggerNativeCameraCapture();
        return;
      }
      captureLiveCameraFrameAndSend('Che, mirá esto y decime qué ves');
    });
  }

  // ============================================================
  // FEED & MENSAJES
  // ============================================================
  function appendHistoryItem(item) {
    if (feedEmpty) feedEmpty.style.display = 'none';

    totalEvents++;
    if (historyCount) historyCount.textContent = `${totalEvents} eventos`;

    let el = document.createElement('div');

    if (item.type === 'user_speech') {
      el.className = 'msg-bubble msg-user';
      el.innerHTML = `<div class="msg-tag">VOS DIJISTE</div><div>${escapeHtml(item.text)}</div>`;
    } else if (item.type === 'assistant_speech') {
      el.className = 'msg-bubble msg-assistant';
      el.innerHTML = `<div class="msg-tag">CHE ASISTENTE</div><div>${escapeHtml(item.text)}</div>`;
    } else if (item.type === 'tool_execution') {
      el.className = 'tool-card';
      const argStr = item.args ? Object.entries(item.args).map(([k, v]) => `${k}: ${v}`).join(', ') : '';
      el.innerHTML = `<span class="tool-badge">ACCIÓN</span><span><strong>${escapeHtml(item.tool)}</strong> (${escapeHtml(argStr)}) ${item.result ? '➔ ' + escapeHtml(item.result) : ''}</span>`;
    }

    if (feedScroll) {
      feedScroll.appendChild(el);
      feedScroll.scrollTop = feedScroll.scrollHeight;
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function sendWs(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  }

  // Botones de control e interrupción táctil
  if (btnPushToTalk) btnPushToTalk.addEventListener('click', triggerMobileMic);
  if (coreOrb) coreOrb.addEventListener('click', triggerMobileMic);
  if (btnTestVoice) btnTestVoice.addEventListener('click', () => sendWs({ type: 'test_voice' }));
  if (btnStopVoice) btnStopVoice.addEventListener('click', () => sendWs({ type: 'stop_speaking' }));

  // ============================================================
  // GESTOS Y MODO PANTALLA COMPLETA INMERSIVA (CARA PURA)
  // ============================================================
  const gestureToast = document.getElementById('gestureToast');
  let toastTimer = null;

  function showToast(msg, isGreen = false) {
    if (!gestureToast) return;
    gestureToast.textContent = msg;
    gestureToast.className = 'gesture-toast show' + (isGreen ? ' green' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      gestureToast.classList.remove('show');
    }, 1800);
  }

  // Prevenir menú contextual en Android para no cortar la pulsación larga
  window.addEventListener('contextmenu', (e) => e.preventDefault());

  function toggleFullscreenMode() {
    const isFull = body.classList.toggle('fullscreen-mode');
    const el = document.documentElement;

    if (isFull) {
      const req = el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen || el.msRequestFullscreen;
      if (req && !document.fullscreenElement && !document.webkitFullscreenElement) {
        try { req.call(el); } catch (e) {}
      }
      showToast('⛶ PANTALLA COMPLETA', false);
    } else {
      const exit = document.exitFullscreen || document.webkitExitFullscreen || document.mozCancelFullScreen || document.msExitFullscreen;
      if (exit && (document.fullscreenElement || document.webkitFullscreenElement)) {
        try { exit.call(document); } catch (e) {}
      }
      showToast('CONTROLES VISIBLES', false);
    }
  }

  // Botones flotantes directos (un toque simple en pantalla)
  const btnFloatHandsFree = document.getElementById('btnFloatHandsFree');
  const btnFloatFullscreen = document.getElementById('btnFloatFullscreen');

  if (btnFloatHandsFree) {
    btnFloatHandsFree.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleHandsFree();
      showToast(isHandsFree ? '👂 MANOS LIBRES: ON' : '🎙 TOCAR PARA HABLAR', isHandsFree);
    });
  }

  if (btnFloatFullscreen) {
    btnFloatFullscreen.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleFullscreenMode();
    });
  }

  // Deslizar desde arriba para mostrar temporalmente la barra si está oculta
  let touchStartY = 0;
  let navHideTimer = null;

  window.addEventListener('touchstart', (e) => {
    if (e.touches && e.touches[0]) {
      touchStartY = e.touches[0].clientY;
    }
  }, { passive: true });

  window.addEventListener('touchmove', (e) => {
    if (body.classList.contains('fullscreen-mode') && e.touches && e.touches[0]) {
      const currentY = e.touches[0].clientY;
      if (touchStartY < 80 && (currentY - touchStartY > 40)) {
        body.classList.add('show-nav');
        clearTimeout(navHideTimer);
        navHideTimer = setTimeout(() => {
          body.classList.remove('show-nav');
        }, 4000);
      }
    }
  }, { passive: true });

  // Escuchar toques en TODO el contenedor de la cara (#viewFace)
  const faceArea = document.getElementById('viewFace') || document.getElementById('faceTriggerArea');

  if (faceArea) {
    let touchStartTime = 0;
    let touchStartX = 0;
    let touchStartYPos = 0;
    let hasMoved = false;
    let longTimer = null;
    let didLongPress = false;
    let lastTapTimestamp = 0;

    // GESTOS TÁCTILES EN CELULAR
    faceArea.addEventListener('touchstart', (e) => {
      if (e.target.closest('button') || e.target.closest('nav') || e.target.closest('.floating-controls')) return;

      if (currentInactivityStage !== 'idle') {
        wakeUpWithStartle();
        showToast('👀 ¡TITÁN DESPIERTO!', true);
        didLongPress = true; // Para no disparar touchend ni activar microfono de golpe
        return;
      }
      if (isWakeStartleActive) {
        didLongPress = true;
        return;
      }

      if (e.touches && e.touches.length === 1) {
        const t = e.touches[0];
        touchStartX = t.clientX;
        touchStartYPos = t.clientY;
        touchStartTime = Date.now();
        hasMoved = false;
        didLongPress = false;

        clearTimeout(longTimer);
        longTimer = setTimeout(() => {
          if (!hasMoved) {
            didLongPress = true;
            toggleHandsFree();
            triggerWakePulse();
            showToast(isHandsFree ? '👂 MANOS LIBRES: ON' : '🎙 TOCAR PARA HABLAR', isHandsFree);
          }
        }, 450); // 450ms: pulsación rápida y segura
      }
    }, { passive: true });

    faceArea.addEventListener('touchmove', (e) => {
      if (e.touches && e.touches.length === 1) {
        const t = e.touches[0];
        // Tolerancia de 50px para compensar el temblor natural del dedo en la pantalla táctil
        if (Math.abs(t.clientX - touchStartX) > 50 || Math.abs(t.clientY - touchStartYPos) > 50) {
          hasMoved = true;
          clearTimeout(longTimer);
        }
      }
    }, { passive: true });

    faceArea.addEventListener('touchend', (e) => {
      clearTimeout(longTimer);
      if (didLongPress) {
        didLongPress = false;
        return;
      }
      if (hasMoved) return;

      const now = Date.now();
      const duration = now - touchStartTime;
      if (duration > 600) return;

      const gap = now - lastTapTimestamp;
      lastTapTimestamp = now;

      // 1. Doble toque: alterna Pantalla Completa (hasta 480ms entre toques)
      if (gap < 480) {
        lastTapTimestamp = 0;
        toggleFullscreenMode();
        return;
      }

      // 2. Toque simple:
      // Si Titán está hablando: silenciar inmediatamente
      if (currentState === 'SPEAKING') {
        sendWs({ type: 'interrupt' });
        updateState('LISTENING', 'Te escucho...');
        updateFaceSpeech('Te escucho...');
        showToast('⏹ SILENCIADO', false);
        return;
      }

      // Toque simple en reposo: activar escucha inmediata de Titán
      if (currentState === 'IDLE') {
        if (isRebelMode) {
          triggerRebelRecoil();
        } else {
          triggerFriendTap();
        }
        triggerWakePulse();
        sendWs({ type: 'trigger_listen' });
        showToast(isRebelMode ? '🤬 ¿QUÉ QUERÉS?' : '🎙 ESCUCHANDO...', true);
      }
    }, { passive: true });

    // CLICKS DE RATÓN (PARA PROBAR EN PC)
    let clickTimeout = null;
    let clickCount = 0;

    faceArea.addEventListener('click', (e) => {
      if (e.target.closest('button') || e.target.closest('nav')) return;

      if (currentInactivityStage !== 'idle') {
        wakeUpWithStartle();
        showToast('👀 ¡TITÁN DESPIERTO!', true);
        return;
      }
      if (isWakeStartleActive) return;

      clickCount++;
      if (clickCount === 1) {
        clickTimeout = setTimeout(() => {
          clickCount = 0;
          if (currentState === 'SPEAKING') {
            sendWs({ type: 'interrupt' });
            updateState('LISTENING', 'Te escucho...');
            showToast('⏹ SILENCIADO', false);
          } else if (!isHandsFree && currentState === 'IDLE') {
            if (isRebelMode) {
              triggerRebelRecoil();
            } else {
              triggerFriendTap();
            }
            triggerMobileMic();
          }
        }, 280);
      } else if (clickCount === 2) {
        clearTimeout(clickTimeout);
        clickCount = 0;
        toggleFullscreenMode();
      }
    });
  }

  const btnToggleFullscreen = document.getElementById('btnToggleFullscreen') || document.getElementById('btnFullscreen');
  if (btnToggleFullscreen) {
    btnToggleFullscreen.addEventListener('click', toggleFullscreenMode);
  }

  const btnMuteAudioEl = document.getElementById('btnMuteAudio');
  if (btnMuteAudioEl) {
    btnMuteAudioEl.addEventListener('click', toggleBrowserAudioMute);
  }
  const btnFloatMuteAudioEl = document.getElementById('btnFloatMuteAudio');
  if (btnFloatMuteAudioEl) {
    btnFloatMuteAudioEl.addEventListener('click', toggleBrowserAudioMute);
  }
  updateMuteButtonUI();

  // Expansión / Reducción de Chat a Pantalla Completa
  const btnExpandChat = document.getElementById('btnExpandChat');
  const viewOrb = document.getElementById('viewOrb');
  if (btnExpandChat && viewOrb) {
    btnExpandChat.addEventListener('click', () => {
      const isExpanded = viewOrb.classList.toggle('chat-expanded');
      btnExpandChat.textContent = isExpanded ? '🗖 Reducir' : '⛶ Extender';
      btnExpandChat.title = isExpanded ? 'Reducir chat y mostrar el orbe' : 'Extender chat a pantalla completa';
      if (isExpanded && feedScroll) {
        setTimeout(() => { feedScroll.scrollTop = feedScroll.scrollHeight; }, 100);
      }
    });
  }

  // Alternar Modo Imagen en la Barra de Comandos con 🎨
  const btnToggleImageMode = document.getElementById('btnToggleImageMode');
  if (btnToggleImageMode && cmdInput) {
    btnToggleImageMode.addEventListener('click', () => {
      if (cmdInput.value.startsWith('/imagen ')) {
        cmdInput.value = cmdInput.value.replace('/imagen ', '');
        btnToggleImageMode.classList.remove('active');
      } else {
        cmdInput.value = '/imagen ' + cmdInput.value;
        btnToggleImageMode.classList.add('active');
        cmdInput.focus();
      }
    });
  }

  // Lightbox Modal para ver imágenes en grande
  const btnCloseLightbox = document.getElementById('btnCloseLightbox');
  const imageLightboxModal = document.getElementById('imageLightboxModal');
  if (btnCloseLightbox && imageLightboxModal) {
    btnCloseLightbox.addEventListener('click', () => {
      imageLightboxModal.classList.remove('active');
    });
    imageLightboxModal.addEventListener('click', (e) => {
      if (e.target === imageLightboxModal) {
        imageLightboxModal.classList.remove('active');
      }
    });
  }

  function handleImageGenerating(msg) {
    if (feedEmpty) feedEmpty.style.display = 'none';
    const existing = document.getElementById('imgGeneratingCard');
    if (existing) existing.remove();

    const card = document.createElement('div');
    card.id = 'imgGeneratingCard';
    card.className = 'msg-image-card';
    card.innerHTML = `
      <div class="card-badge">🎨 CREANDO IMAGEN CON IA...</div>
      <div class="card-prompt"><em>"${escapeHtml(msg.prompt)}"</em></div>
      <div style="display:flex;align-items:center;gap:0.6rem;color:var(--neon-cyan);font-size:0.8rem;margin-top:0.4rem;">
        <span>⏳</span> Generando con Flux en alta definición (1024x1024)...
      </div>
    `;
    if (feedScroll) {
      feedScroll.appendChild(card);
      feedScroll.scrollTop = feedScroll.scrollHeight;
    }
  }

  function handleImageGenerated(msg) {
    if (feedEmpty) feedEmpty.style.display = 'none';
    const generatingCard = document.getElementById('imgGeneratingCard');
    if (generatingCard) {
      generatingCard.remove();
    }

    totalEvents++;
    if (historyCount) historyCount.textContent = `${totalEvents} eventos`;

    const card = document.createElement('div');
    card.className = 'msg-image-card';
    const imgUrl = msg.url;
    const promptText = msg.prompt || 'Imagen IA';
    const filename = msg.filename || 'titan_art.jpg';
    const timeStr = msg.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    card.innerHTML = `
      <div class="card-badge">
        <span>🎨 TITÁN ART // FLUX IA</span>
        <span style="margin-left:auto;color:var(--text-muted);font-size:0.65rem;">${escapeHtml(timeStr)}</span>
      </div>
      <div class="img-preview-box" title="Clic para ver en grande">
        <img src="${escapeHtml(imgUrl)}" alt="${escapeHtml(promptText)}" loading="lazy">
      </div>
      <div class="card-prompt">
        <strong>"${escapeHtml(promptText)}"</strong>
      </div>
      <div class="card-actions">
        <a href="${escapeHtml(imgUrl)}" download="${escapeHtml(filename)}" class="btn-img-action primary" title="Descargar imagen a máxima resolución">
          <span>⬇️</span> Descargar
        </a>
        <button type="button" class="btn-img-action btn-lightbox-trigger" title="Ver en pantalla completa">
          <span>🔍</span> Ver en Grande
        </button>
        <button type="button" class="btn-img-action btn-wallpaper-trigger" title="Poner como fondo de pantalla de Windows">
          <span>🖥️</span> Wallpaper
        </button>
      </div>
    `;

    const openLightbox = () => {
      const modal = document.getElementById('imageLightboxModal');
      const lImg = document.getElementById('lightboxImg');
      const lCap = document.getElementById('lightboxCaption');
      if (modal && lImg) {
        lImg.src = imgUrl;
        if (lCap) lCap.textContent = promptText;
        modal.classList.add('active');
      }
    };

    const previewBox = card.querySelector('.img-preview-box');
    if (previewBox) previewBox.addEventListener('click', openLightbox);

    const btnLb = card.querySelector('.btn-lightbox-trigger');
    if (btnLb) btnLb.addEventListener('click', openLightbox);

    const btnWp = card.querySelector('.btn-wallpaper-trigger');
    if (btnWp) {
      btnWp.addEventListener('click', async () => {
        btnWp.textContent = '⏳ Aplicando...';
        btnWp.style.pointerEvents = 'none';
        try {
          const res = await fetch('/api/pc/wallpaper/set', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_url: imgUrl })
          });
          const data = await res.json();
          if (res.ok && data.status === 'success') {
            if (typeof showToast === 'function') {
              showToast('🖥️ ¡Fondo de pantalla de Windows actualizado!', true);
            }
            btnWp.innerHTML = '<span>✅</span> Wallpaper';
          } else {
            if (typeof showToast === 'function') {
              showToast(data.message || data.detail || 'No se pudo cambiar el fondo de pantalla.', false);
            }
            btnWp.innerHTML = '<span>🖥️</span> Wallpaper';
          }
        } catch (err) {
          console.error('Error aplicando wallpaper:', err);
          if (typeof showToast === 'function') {
            showToast('Error de conexión al aplicar fondo.', false);
          }
          btnWp.innerHTML = '<span>🖥️</span> Wallpaper';
        } finally {
          btnWp.style.pointerEvents = '';
        }
      });
    }

    if (feedScroll) {
      feedScroll.appendChild(card);
      feedScroll.scrollTop = feedScroll.scrollHeight;
    }
  }

  async function triggerImageGeneration(prompt) {
    handleImageGenerating({ prompt: prompt });
    try {
      const res = await fetch('/api/image/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: prompt })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Error generando imagen');
      }
    } catch (e) {
      console.error('Error generando imagen:', e);
      const genCard = document.getElementById('imgGeneratingCard');
      if (genCard) {
        genCard.innerHTML = `<div class="card-badge" style="color:var(--neon-red);">⚠️ ERROR AL CREAR IMAGEN</div><div class="card-prompt">${escapeHtml(e.message || 'No se pudo generar la imagen.')}</div>`;
      }
    }
  }

  if (commandForm) {
    commandForm.addEventListener('submit', (e) => {
      e.preventDefault();
      const txt = cmdInput.value.trim();
      if (!txt) return;

      const normTxt = txt.toLowerCase();
      const isImgCmd = normTxt.startsWith('/imagen') || normTxt.startsWith('/dibujar') || normTxt.startsWith('dibujame ') || normTxt.startsWith('creame una imagen ') || normTxt.startsWith('crea una imagen ');

      if (isImgCmd) {
        let p = txt;
        for (const pfx of ['/imagen', '/dibujar', 'dibujame', 'creame una imagen de', 'creame una imagen', 'crea una imagen de', 'crea una imagen']) {
          if (normTxt.startsWith(pfx)) {
            p = txt.slice(pfx.length).trim();
            break;
          }
        }
        if (p) {
          appendHistoryItem({
            type: 'user_speech',
            text: `🎨 /imagen ${p}`
          });
          cmdInput.value = '';
          if (btnToggleImageMode) btnToggleImageMode.classList.remove('active');
          triggerImageGeneration(p);
          return;
        }
      }

      sendWs({ type: 'chat_prompt', text: txt });
      cmdInput.value = '';
      if (btnToggleImageMode) btnToggleImageMode.classList.remove('active');
    });
  }

  // Acciones rápidas de telemetría
  const btnTelemAnalyzeScreen = document.getElementById('btnTelemAnalyzeScreen');
  if (btnTelemAnalyzeScreen) {
    btnTelemAnalyzeScreen.addEventListener('click', async () => {
      try {
        btnTelemAnalyzeScreen.style.opacity = '0.6';
        btnTelemAnalyzeScreen.textContent = '👁️ Mirando...';
        if (typeof showToast === 'function') {
          showToast('Titán está mirando la pantalla de tu PC...', true);
        }
        const res = await fetch('/api/pc/screen/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: 'Describí qué hay en la pantalla y qué error o información se muestra' })
        });
        const data = await res.json();
        if (res.ok && data.reply) {
          if (typeof showToast === 'function') {
            showToast(`👁️ Titán: ${data.reply.slice(0, 110)}...`, true);
          }
        } else {
          if (typeof showToast === 'function') {
            showToast(data.detail || 'No se pudo analizar la pantalla.', false);
          }
        }
      } catch (e) {
        console.error("Error analizando pantalla:", e);
        if (typeof showToast === 'function') {
          showToast('Error de conexión al mirar la pantalla.', false);
        }
      } finally {
        btnTelemAnalyzeScreen.style.opacity = '1';
        btnTelemAnalyzeScreen.textContent = '👁️ Mirar Pantalla';
      }
    });
  }

  const btnTelemToggleVoice = document.getElementById('btnTelemToggleVoice');
  if (btnTelemToggleVoice) {
    btnTelemToggleVoice.addEventListener('click', async () => {
      try {
        btnTelemToggleVoice.style.opacity = '0.7';
        const res = await fetch('/api/pc/voice/toggle', { method: 'POST' });
        const data = await res.json();
        if (typeof showToast === 'function') {
          showToast(data.message || 'Cambiando voz en PC...', true);
        }
        await fetchTelemetry();
      } catch (e) {
        console.error("Error al cambiar voz en PC:", e);
      } finally {
        btnTelemToggleVoice.style.opacity = '1';
      }
    });
  }
  if (btnTelemMinimize) btnTelemMinimize.addEventListener('click', () => sendWs({ type: 'chat_prompt', text: 'Minimizá todo' }));
  if (btnTelemLock) btnTelemLock.addEventListener('click', () => sendWs({ type: 'chat_prompt', text: 'Bloqueá la compu' }));
  if (btnTelemScreenshot) btnTelemScreenshot.addEventListener('click', () => sendWs({ type: 'chat_prompt', text: 'Sacá una captura de pantalla' }));

  // Modal Settings
  if (btnOpenSettings) btnOpenSettings.addEventListener('click', () => modalBackdrop.classList.add('active'));
  if (btnCloseModal) btnCloseModal.addEventListener('click', () => modalBackdrop.classList.remove('active'));
  if (modalBackdrop) {
    modalBackdrop.addEventListener('click', (e) => {
      if (e.target === modalBackdrop) modalBackdrop.classList.remove('active');
    });
  }

  if (btnSaveKey) {
    btnSaveKey.addEventListener('click', async () => {
      const key = apiKeyInput.value.trim();
      if (!key) return;
      try {
        const res = await fetch('/api/key', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ api_key: key })
        });
        if (res.ok) {
          keyStatusMsg.style.color = 'var(--neon-green)';
          keyStatusMsg.textContent = '¡Clave guardada!';
          setTimeout(() => modalBackdrop.classList.remove('active'), 1200);
        }
      } catch (e) {}
    });
  }

  // ============================================================
  // POLLING DE TELEMETRÍA DUAL (PC PRINCIPAL + SERVIDOR TITÁN DDR3)
  // ============================================================
  function updateTempBadge(badgeEl, tempC) {
    if (!badgeEl) return;
    if (tempC !== undefined && tempC !== null && tempC > 0) {
      badgeEl.textContent = `${tempC} °C`;
      badgeEl.className = 'temp-badge ' + (tempC >= 80 ? 'temp-danger' : tempC >= 68 ? 'temp-warning' : 'temp-normal');
      badgeEl.style.display = 'inline-block';
    } else {
      badgeEl.textContent = '-- °C';
      badgeEl.className = 'temp-badge temp-normal';
    }
  }

  async function fetchTelemetry() {
    try {
      const res = await fetch('/api/metrics');
      if (!res.ok) return;
      const data = await res.json();
      
      const primary = data.primary || {};
      const ddr3 = data.ddr3 || {};
      const isPrimaryConnected = !!primary.connected;

      // 1. PC PRINCIPAL (WINDOWS)
      const pcBadge = document.getElementById('pcStatusBadge');
      const pcStatusText = document.getElementById('pcStatusText');
      const pcHostLabel = document.getElementById('pcHostnameLabel');
      if (pcBadge && pcStatusText) {
        if (isPrimaryConnected) {
          pcBadge.className = 'telem-status-badge badge-online';
          pcStatusText.textContent = 'CONECTADA';
        } else {
          pcBadge.className = 'telem-status-badge badge-offline';
          pcStatusText.textContent = 'EN REPOSO / SATÉLITE OFF';
        }
      }
      if (pcHostLabel && primary.hostname) {
        pcHostLabel.textContent = `${primary.hostname} // Windows`;
      }

      // CPU PC Principal
      const telemCpuTotal = document.getElementById('telemCpuTotal');
      const barCpuTotal = document.getElementById('barCpuTotal');
      const telemCpuFreq = document.getElementById('telemCpuFreq');
      const telemCpuCores = document.getElementById('telemCpuCores');
      const telemCpuTemp = document.getElementById('telemCpuTemp');
      const coresGrid = document.getElementById('coresGrid');

      if (telemCpuTotal) telemCpuTotal.textContent = isPrimaryConnected ? `${primary.cpu_percent || 0}%` : '--%';
      if (barCpuTotal) barCpuTotal.style.width = isPrimaryConnected ? `${primary.cpu_percent || 0}%` : '0%';
      if (telemCpuFreq) telemCpuFreq.textContent = isPrimaryConnected && primary.cpu_freq_ghz ? `${primary.cpu_freq_ghz} GHz` : '-- GHz';
      if (telemCpuCores) telemCpuCores.textContent = isPrimaryConnected && primary.cpu_count ? `${primary.cpu_count} hilos` : '--';
      
      // Control de Temperatura PC Principal (Badge CPU)
      updateTempBadge(telemCpuTemp, isPrimaryConnected ? (primary.temp_c || primary.cpu_temp_c) : null);

      // Tarjeta de Control Térmico y Refrigeración (PC Principal)
      const thermalTempValue = document.getElementById('thermalTempValue');
      const thermalPlanLabel = document.getElementById('thermalPlanLabel');
      const thermalStatusBadge = document.getElementById('thermalStatusBadge');
      const thermalBarFill = document.getElementById('thermalBarFill');
      const thermalCpuVal = document.getElementById('thermalCpuVal');
      const thermalGpuVal = document.getElementById('thermalGpuVal');
      const thermalMaxVal = document.getElementById('thermalMaxVal');

      const rawTemp = isPrimaryConnected ? (primary.temp_c ?? primary.cpu_temp_c) : null;
      const currentTemp = (rawTemp !== null && rawTemp !== undefined && !isNaN(Number(rawTemp))) ? Number(rawTemp) : null;
      const powerPlan = primary.power_plan || {};

      if (thermalTempValue) {
        thermalTempValue.textContent = currentTemp !== null ? `${currentTemp.toFixed(1)}°C` : '--.-°C';
      }
      if (thermalPlanLabel) {
        const pName = powerPlan.name || 'Equilibrado';
        const pMode = powerPlan.mode || 'balanced';
        const pIcon = pMode === 'eco' ? '❄️' : (pMode === 'performance' ? '🚀' : '⚖️');
        thermalPlanLabel.textContent = `${pIcon} ${pName}`;
      }
      if (thermalStatusBadge) {
        if (!isPrimaryConnected || currentTemp === null) {
          thermalStatusBadge.textContent = 'OFFLINE';
          thermalStatusBadge.className = 'thermal-badge';
        } else if (currentTemp < 55) {
          thermalStatusBadge.textContent = '🟢 ÓPTIMA (<55°C)';
          thermalStatusBadge.className = 'thermal-badge badge-optimal';
        } else if (currentTemp < 75) {
          thermalStatusBadge.textContent = '🟡 TEMPLADA (55-75°C)';
          thermalStatusBadge.className = 'thermal-badge badge-warm';
        } else {
          thermalStatusBadge.textContent = '🔴 ALERTA TÉRMICA';
          thermalStatusBadge.className = 'thermal-badge badge-alert';
        }
      }
      if (thermalBarFill) {
        if (currentTemp !== null) {
          const pct = Math.min(100, Math.max(5, Math.round(((currentTemp - 30) / 60) * 100)));
          thermalBarFill.style.width = `${pct}%`;
        } else {
          thermalBarFill.style.width = '0%';
        }
      }
      if (thermalCpuVal) {
        const cpuRaw = isPrimaryConnected ? (primary.cpu_temp_c ?? currentTemp) : null;
        const cpuNum = (cpuRaw !== null && cpuRaw !== undefined && !isNaN(Number(cpuRaw))) ? Number(cpuRaw) : null;
        thermalCpuVal.textContent = cpuNum !== null ? `${cpuNum.toFixed(1)}°C` : '--.-°C';
      }
      if (thermalGpuVal) {
        const gpuRaw = isPrimaryConnected ? (primary.gpu_temp_c ?? currentTemp) : null;
        const gpuNum = (gpuRaw !== null && gpuRaw !== undefined && !isNaN(Number(gpuRaw))) ? Number(gpuRaw) : null;
        thermalGpuVal.textContent = gpuNum !== null ? `${gpuNum.toFixed(1)}°C` : '--.-°C';
      }
      if (thermalMaxVal) {
        const maxRaw = isPrimaryConnected ? (primary.max_temp_c ?? currentTemp) : null;
        const maxNum = (maxRaw !== null && maxRaw !== undefined && !isNaN(Number(maxRaw))) ? Number(maxRaw) : null;
        thermalMaxVal.textContent = maxNum !== null ? `${maxNum.toFixed(1)}°C` : '--.-°C';
      }

      // Sincronizar botones de perfil térmico
      const activeMode = powerPlan.mode || 'balanced';
      const btnPlanEco = document.getElementById('btnPlanEco');
      const btnPlanBalanced = document.getElementById('btnPlanBalanced');
      const btnPlanPerf = document.getElementById('btnPlanPerf');
      if (btnPlanEco) btnPlanEco.classList.toggle('active', activeMode === 'eco');
      if (btnPlanBalanced) btnPlanBalanced.classList.toggle('active', activeMode === 'balanced');
      if (btnPlanPerf) btnPlanPerf.classList.toggle('active', activeMode === 'performance');

      // Alarma Térmica por umbral
      const alarmThresholdSelect = document.getElementById('thermalAlarmThreshold');
      if (alarmThresholdSelect && currentTemp !== null) {
        const threshold = parseFloat(alarmThresholdSelect.value) || 75.0;
        const nowMs = Date.now();
        if (currentTemp >= threshold && (!fetchTelemetry._lastAlarmTime || (nowMs - fetchTelemetry._lastAlarmTime) > 120000)) {
          fetchTelemetry._lastAlarmTime = nowMs;
          if (typeof showToast === 'function') {
            showToast(`⚠️ ALERTA TÉRMICA: PC a ${currentTemp}°C`, false);
          }
        }
      }

      if (coresGrid) {
        if (isPrimaryConnected && primary.per_cpu) {
          coresGrid.innerHTML = '';
          primary.per_cpu.forEach((c) => {
            const b = document.createElement('div');
            b.className = 'core-bar';
            b.innerHTML = `<div class="core-bar-fill" style="height: ${c}%;"></div>`;
            coresGrid.appendChild(b);
          });
        } else if (!isPrimaryConnected) {
          coresGrid.innerHTML = '<span style="font-size: 10px; color: var(--text-muted); padding: 4px 0;">Iniciá el satélite en Windows para ver núcleos.</span>';
        }
      }

      // RAM PC Principal
      const telemRamPercent = document.getElementById('telemRamPercent');
      const barRam = document.getElementById('barRam');
      const telemRamUsed = document.getElementById('telemRamUsed');
      const telemRamFree = document.getElementById('telemRamFree');
      const telemRamTotal = document.getElementById('telemRamTotal');

      if (telemRamPercent) telemRamPercent.textContent = isPrimaryConnected ? `${primary.ram_percent || 0}%` : '--%';
      if (barRam) barRam.style.width = isPrimaryConnected ? `${primary.ram_percent || 0}%` : '0%';
      if (telemRamUsed) telemRamUsed.textContent = isPrimaryConnected && primary.ram_used_gb !== undefined ? `${primary.ram_used_gb} GB` : '-- GB';
      if (telemRamFree) telemRamFree.textContent = isPrimaryConnected && primary.ram_free_gb !== undefined ? `${primary.ram_free_gb} GB` : '-- GB';
      if (telemRamTotal) telemRamTotal.textContent = isPrimaryConnected && primary.ram_total_gb !== undefined ? `${primary.ram_total_gb} GB` : '-- GB';

      // Discos PC Principal
      const disksList = document.getElementById('disksList');
      if (disksList) {
        if (isPrimaryConnected && primary.disks && Object.keys(primary.disks).length > 0) {
          disksList.innerHTML = '';
          Object.entries(primary.disks).forEach(([letter, d]) => {
            const itm = document.createElement('div');
            itm.className = 'disk-item';
            itm.innerHTML = `
              <div class="disk-info">
                <span>Disco ${letter}:</span>
                <span>${d.free_gb} GB libres (${100 - d.percent_used}%)</span>
              </div>
              <div class="progress-bar-bg">
                <div class="progress-bar-fill" style="width: ${d.percent_used}%;"></div>
              </div>
            `;
            disksList.appendChild(itm);
          });
        } else if (!isPrimaryConnected) {
          disksList.innerHTML = '<div style="font-size: 11px; color: var(--text-muted); padding: 6px 0;">Iniciá el satélite en la PC para ver discos.</div>';
        }
      }

      // Red PC Principal
      const telemNetRecv = document.getElementById('telemNetRecv');
      const telemNetSent = document.getElementById('telemNetSent');
      if (telemNetRecv) telemNetRecv.textContent = isPrimaryConnected && primary.net_recv_mb !== undefined ? `${primary.net_recv_mb} MB` : '-- MB';
      if (telemNetSent) telemNetSent.textContent = isPrimaryConnected && primary.net_sent_mb !== undefined ? `${primary.net_sent_mb} MB` : '-- MB';

      // Estado de Botón Mirar Pantalla
      const btnTelemAnalyzeScreen = document.getElementById('btnTelemAnalyzeScreen');
      if (btnTelemAnalyzeScreen) {
        btnTelemAnalyzeScreen.disabled = !isPrimaryConnected;
      }

      // Estado de Voz en PC Principal
      const btnTelemToggleVoice = document.getElementById('btnTelemToggleVoice');
      if (btnTelemToggleVoice) {
        if (isPrimaryConnected) {
          btnTelemToggleVoice.disabled = false;
          const pcVoiceOn = !!primary.pc_voice_enabled;
          btnTelemToggleVoice.textContent = pcVoiceOn ? '🔊 Voz en PC: ON' : '🔇 Voz en PC: OFF';
          btnTelemToggleVoice.style.color = pcVoiceOn ? 'var(--neon-green)' : 'var(--text-muted)';
          btnTelemToggleVoice.style.borderColor = pcVoiceOn ? 'rgba(0, 255, 136, 0.5)' : '';
        } else {
          btnTelemToggleVoice.disabled = true;
          btnTelemToggleVoice.textContent = '🔇 Voz en PC: OFF';
          btnTelemToggleVoice.style.color = 'var(--text-muted)';
          btnTelemToggleVoice.style.borderColor = '';
        }
      }


      // 2. SERVIDOR TITÁN (DDR3)
      const serverHostLabel = document.getElementById('serverHostLabel');
      if (serverHostLabel && ddr3.hostname) {
        serverHostLabel.textContent = `${ddr3.hostname} // Ubuntu Linux (192.168.100.5)`;
      }

      const serverCpuVal = document.getElementById('serverCpuVal');
      const barServerCpu = document.getElementById('barServerCpu');
      const serverCpuTemp = document.getElementById('serverCpuTemp');
      const serverCpuCores = document.getElementById('serverCpuCores');

      if (serverCpuVal) serverCpuVal.textContent = `${ddr3.cpu_percent || 0}%`;
      if (barServerCpu) barServerCpu.style.width = `${ddr3.cpu_percent || 0}%`;
      if (serverCpuCores) serverCpuCores.textContent = `${ddr3.cpu_count || '--'} hilos`;
      updateTempBadge(serverCpuTemp, ddr3.temp_c || ddr3.cpu_temp_c);

      const serverRamVal = document.getElementById('serverRamVal');
      const barServerRam = document.getElementById('barServerRam');
      const serverRamUsed = document.getElementById('serverRamUsed');
      const serverRamTotal = document.getElementById('serverRamTotal');

      if (serverRamVal) serverRamVal.textContent = `${ddr3.ram_percent || 0}%`;
      if (barServerRam) barServerRam.style.width = `${ddr3.ram_percent || 0}%`;
      if (serverRamUsed) serverRamUsed.textContent = ddr3.ram_used_gb !== undefined ? `${ddr3.ram_used_gb} GB` : '-- GB';
      if (serverRamTotal) serverRamTotal.textContent = ddr3.ram_total_gb !== undefined ? `${ddr3.ram_total_gb} GB` : '-- GB';

      const serverDiskVal = document.getElementById('serverDiskVal');
      const barServerDisk = document.getElementById('barServerDisk');
      const serverDiskFree = document.getElementById('serverDiskFree');
      const serverDiskTotal = document.getElementById('serverDiskTotal');

      const rootDisk = (ddr3.disks && (ddr3.disks['/'] || Object.values(ddr3.disks)[0])) || {};
      if (serverDiskVal) serverDiskVal.textContent = rootDisk.percent_used !== undefined ? `${rootDisk.percent_used}%` : '--%';
      if (barServerDisk) barServerDisk.style.width = rootDisk.percent_used !== undefined ? `${rootDisk.percent_used}%` : '0%';
      if (serverDiskFree) serverDiskFree.textContent = rootDisk.free_gb !== undefined ? `${rootDisk.free_gb} GB` : '-- GB';
      if (serverDiskTotal) serverDiskTotal.textContent = rootDisk.total_gb !== undefined ? `${rootDisk.total_gb} GB` : '-- GB';

      const serverNetRecv = document.getElementById('serverNetRecv');
      const serverNetSent = document.getElementById('serverNetSent');
      if (serverNetRecv) serverNetRecv.textContent = ddr3.net_recv_mb !== undefined ? `${ddr3.net_recv_mb} MB` : '-- MB';
      if (serverNetSent) serverNetSent.textContent = ddr3.net_sent_mb !== undefined ? `${ddr3.net_sent_mb} MB` : '-- MB';

    } catch (e) {
      console.warn("Error actualizando telemetría dual:", e);
    }
  }

  // Polling continuo de telemetría dual (PC Principal Windows + Servidor DDR3) cada 2.5s
  fetchTelemetry();
  setInterval(fetchTelemetry, 2500);

  function initThermalControls() {
    const btnCoolDown = document.getElementById('btnCoolDown');
    if (btnCoolDown) {
      btnCoolDown.addEventListener('click', async () => {
        const originalText = btnCoolDown.innerHTML;
        btnCoolDown.innerHTML = '<span class="cool-icon">❄️</span><span>REFRIGERANDO...</span>';
        btnCoolDown.style.pointerEvents = 'none';
        btnCoolDown.style.opacity = '0.8';
        if (typeof showToast === 'function') {
          showToast('❄️ Refrigerando PC: pasando a Modo Frío...', true);
        }
        try {
          const res = await fetch('/api/pc/thermal/cool-down', { method: 'POST' });
          const data = await res.json();
          if (typeof showToast === 'function') {
            showToast(data.message || '❄️ Modo Frío aplicado con éxito', true);
          }
          await fetchTelemetry();
        } catch (e) {
          console.error("Error al enfriar PC:", e);
          if (typeof showToast === 'function') {
            showToast('❌ Error al enfriar la PC', false);
          }
        } finally {
          setTimeout(() => {
            btnCoolDown.innerHTML = originalText;
            btnCoolDown.style.pointerEvents = '';
            btnCoolDown.style.opacity = '';
          }, 1500);
        }
      });
    }

    const profileBtns = document.querySelectorAll('.btn-thermal-profile');
    profileBtns.forEach(btn => {
      btn.addEventListener('click', async () => {
        const mode = btn.getAttribute('data-mode') || 'balanced';
        profileBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        if (typeof showToast === 'function') {
          const label = mode === 'eco' ? '❄️ Modo Frío' : (mode === 'performance' ? '🚀 Alto Rendimiento' : '⚖️ Equilibrado');
          showToast(`Cambiando a ${label}...`, true);
        }
        try {
          const res = await fetch('/api/pc/thermal/power-plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plan_mode: mode })
          });
          const data = await res.json();
          if (typeof showToast === 'function' && data.message) {
            showToast(data.message, true);
          }
          await fetchTelemetry();
        } catch (e) {
          console.error("Error cambiando plan de energía:", e);
        }
      });
    });
  }

  // Iniciar controles térmicos
  initThermalControls();

  // Iniciar barra de modos
  initModeBar();

  // Iniciar controlador de pantalla limpia (auto-ocultamiento para J2)
  initCleanScreenController();

  // Iniciar tracker de inactividad (15 min Mate, 30 min Modorra, 45 min Siesta)
  initInactivityTracker();

  // Iniciar socket
  connectWebSocket();

  // Restaurar Manos Libres si estaba activo (con el primer gesto del usuario para Chrome)
  try {
    if (localStorage.getItem('titan_hands_free') === '1') {
      const activateOnGesture = () => {
        setHandsFree(true);
        window.removeEventListener('click', activateOnGesture);
        window.removeEventListener('touchstart', activateOnGesture);
      };
      window.addEventListener('click', activateOnGesture, { once: true });
      window.addEventListener('touchstart', activateOnGesture, { once: true });
    }
  } catch (e) {}
});
