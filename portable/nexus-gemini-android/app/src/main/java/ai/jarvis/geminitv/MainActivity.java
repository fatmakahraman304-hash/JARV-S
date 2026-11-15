package ai.jarvis.geminitv;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.text.InputType;
import android.view.KeyEvent;
import android.view.inputmethod.EditorInfo;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Locale;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/**
 * Foreground-only, button-free voice interaction prototype.
 * Android SpeechRecognizer is NOT designed as a reliable continuous hotword
 * engine. Best-effort short recognition sessions are restarted in foreground.
 * In sleep mode, only a recognized wake command resumes conversation.
 */
public final class MainActivity extends Activity {
    private static final int OPEN_KEY_FILE = 110;
    private static final int MIC_PERMISSION = 130;
    private static final long SESSION_TIMEOUT_MS = 20000L;
    private static final int MAX_SERVICE_FAILURES = 5;
    private static final int SKY = Color.rgb(123, 223, 255);
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ThreadPoolExecutor worker = new ThreadPoolExecutor(
            0, 2, 30, TimeUnit.SECONDS, new SynchronousQueue<>());
    private final JSONArray history = new JSONArray();
    private boolean listening = false;
    private final Runnable microphoneTimeout = () -> {
        if (listening) {
            releaseRecognizer();
            retrySpeech("Konuşma tanıma hizmeti yanıt vermedi.");
        }
    };
    private final Runnable nextListen = this::startRecognition;
    private final Runnable requestTimeout = this::onRequestTimeout;
    private final Runnable speechTimeout = this::onSpeechTimeout;

    private TextView status, conversation, micIndicator;
    private EditText prompt, manualKey;
    private Button keyPicker, manualSave, replaceKey;
    private Spinner model;
    private SpeechRecognizer recognizer;
    private TextToSpeech tts;
    private String apiKey;
    private boolean foreground = false;
    private boolean destroyed = false;
    private boolean speaking = false;
    private GeminiHttp.Call activeRequest;
    private Future<?> activeTask;
    private boolean editingKey;
    private boolean voiceEnabled = true;
    private boolean sleeping;
    private boolean permissionRequested;
    private boolean recognitionBlocked;
    private long utteranceSequence;
    private String activeUtterance;
    private boolean ttsReady = false;
    private boolean greetingPlayed = false;
    private int serviceFailures = 0;

    private TextView makeText(String title, int sp, int color) {
        TextView value = new TextView(this);
        value.setText(title);
        value.setTextSize(sp);
        value.setTextColor(color);
        value.setPadding(0, 12, 0, 12);
        return value;
    }

    private void setStatus(String value) {
        if (status != null) status.setText(value);
    }

    private void setMic(String value) {
        if (micIndicator != null) micIndicator.setText(value);
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
        if (state != null) {
            sleeping = state.getBoolean("sleeping");
            voiceEnabled = state.getBoolean("voiceEnabled", true);
            permissionRequested = state.getBoolean("permissionRequested");
            editingKey = state.getBoolean("editingKey");
        }
        try { apiKey = DeviceKeyStore.load(this); }
        catch (Exception ignored) { apiKey = null; }

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(Color.rgb(6, 17, 29));
        LinearLayout root = new LinearLayout(this);
        root.setPadding(30, 20, 30, 28);
        root.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(root);
        setContentView(scroll);

        root.addView(makeText("J.A.R.V.I.S.", 40, SKY));
        root.addView(makeText("NEXUS · GEMINI · ELLER SERBEST SES MODU", 17, Color.LTGRAY));
        status = makeText("Başlatılıyor…", 20, SKY);
        root.addView(status);
        micIndicator = makeText("● MİKROFON KAPALI", 20, Color.rgb(245, 187, 131));
        root.addView(micIndicator);
        root.addView(makeText("Uyu / JARVIS uyan · Bekleme modu\nSus / Konuş · Yanıt sesi",
                20, Color.WHITE));

        root.addView(makeText("Cihaz komutları · Chrome’u aç · Sesi yükselt · YouTube’da caz ara",
                17, Color.LTGRAY));

        keyPicker = new Button(this);
        keyPicker.setText("Gemini anahtar dosyasını seç · İlk kurulum");
        keyPicker.setTextSize(19);
        keyPicker.setMinHeight(68);
        keyPicker.setAllCaps(false);
        root.addView(keyPicker);
        keyPicker.setVisibility(apiKey == null ? Button.VISIBLE : Button.GONE);
        keyPicker.setOnClickListener(v -> chooseKeyFile());

        // First-install fallback for Android projectors without DocumentsUI.
        // Keep the field masked; store only via device-local Android Keystore.
        manualKey = new EditText(this);
        manualKey.setTextColor(Color.WHITE);
        manualKey.setHintTextColor(Color.LTGRAY);
        manualKey.setHint("Dosya seçici yoksa Gemini API anahtarını buraya bir kez gir");
        manualKey.setTextSize(19);
        manualKey.setSingleLine(true);
        manualKey.setInputType(InputType.TYPE_CLASS_TEXT
                | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        manualKey.setMaxLines(1);
        manualKey.setSaveEnabled(false);
        manualKey.setOnFocusChangeListener((field, focused) -> {
            if (focused) {
                ui.removeCallbacks(nextListen);
                releaseRecognizer();
                setMic("● ANAHTAR GİRİLİRKEN MİKROFON KAPALI");
            } else {
                ui.post(this::ensureMicPermission);
            }
        });
        manualKey.setImportantForAutofill(android.view.View.IMPORTANT_FOR_AUTOFILL_NO);
        root.addView(manualKey);
        manualSave = new Button(this);
        manualSave.setText("Gemini anahtarını bir kez kaydet");
        manualSave.setTextSize(18);
        manualSave.setAllCaps(false);
        manualSave.setMinHeight(68);
        root.addView(manualSave);
        manualSave.setOnClickListener(v -> saveManualKey());
        replaceKey = new Button(this);
        replaceKey.setText("Gemini anahtarını değiştir");
        replaceKey.setAllCaps(false);
        replaceKey.setVisibility(android.view.View.GONE);
        replaceKey.setOnClickListener(v -> {
            editingKey = true;
            updateSetupVisibility();
            setStatus("Yeni Gemini API anahtarını gir veya anahtar dosyasını seç.");
            manualKey.requestFocus();
        });
        root.addView(replaceKey);
        updateSetupVisibility();

        model = new Spinner(this);
        ArrayAdapter<String> adapter = new ArrayAdapter<>(this,
                android.R.layout.simple_spinner_item, GeminiHttp.MODELS);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        model.setAdapter(adapter);
        root.addView(makeText("Gemini modeli", 15, Color.LTGRAY));
        root.addView(model);

        conversation = makeText("JARVIS: Merhaba. Sesli konuşmaya hazırım.\n", 21, Color.WHITE);
        conversation.setMinHeight(270);
        conversation.setTextIsSelectable(true);
        root.addView(conversation);

        // Keyboard and remote IME input use the same command pipeline as voice.
        prompt = new EditText(this);
        prompt.setTextColor(Color.WHITE);
        prompt.setHintTextColor(Color.LTGRAY);
        prompt.setHint("Komutu veya soruyu yaz ve Enter’a bas");
        prompt.setTextSize(19);
        prompt.setSingleLine(true);
        prompt.setImeOptions(EditorInfo.IME_ACTION_SEND);
        prompt.setInputType(InputType.TYPE_CLASS_TEXT);
        prompt.setOnEditorActionListener((field, action, event) -> {
            if (action == EditorInfo.IME_ACTION_SEND ||
                    (event != null && event.getKeyCode() == KeyEvent.KEYCODE_ENTER
                            && event.getAction() == KeyEvent.ACTION_DOWN)) {
                String input = prompt.getText().toString();
                if (VoiceControl.classify(input) != VoiceControl.Command.NONE) prompt.setText("");
                handleUtterance(input, false);
                return true;
            }
            return false;
        });
        root.addView(prompt);
        root.addView(makeText("Mikrofon yalnızca uygulama ekrandayken dinler. "
                + "Android konuşma tanıma servisi sesini kendi sunucusuna gönderebilir. "
                + "Soruların metni Gemini API'ye gönderilir. Uygulamayı kapatırsan dinleme durur. "
                + "USB'de şifresiz API anahtarı varsa USB'yi başkalarıyla paylaşma.",
                14, Color.LTGRAY));
        if (apiKey == null) {
            setStatus("İlk kurulum: Gemini API anahtarını gir veya USB'den anahtar dosyasını seç.");
        } else if (sleeping) {
            showSleepStatus();
        } else {
            setStatus("Gemini anahtarı hazır · Türkçe ses başlatılıyor…");
        }
        configureTts();
    }


    private void updateSetupVisibility() {
        boolean setupRequired = apiKey == null || editingKey;
        if (setupRequired) replaceKey.setVisibility(android.view.View.GONE);
        if (keyPicker != null)
            keyPicker.setVisibility(setupRequired ? android.view.View.VISIBLE : android.view.View.GONE);
        if (manualKey != null)
            manualKey.setVisibility(setupRequired ? android.view.View.VISIBLE : android.view.View.GONE);
        if (manualSave != null)
            manualSave.setVisibility(setupRequired ? android.view.View.VISIBLE : android.view.View.GONE);
    }

    private void saveManualKey() {
        if (apiKey != null && !editingKey) return;
        String candidate = manualKey.getText().toString().trim();
        if (!candidate.matches("[\\x21-\\x7e]{20,220}")) {
            setStatus("Gemini API anahtarını eksiksiz gir (20-220 karakter, boşluk yok).");
            return;
        }
        saveKey(candidate);
    }

    private void saveKey(String candidate) {
        try {
            DeviceKeyStore.save(this, candidate);
        } catch (Exception e) {
            setStatus("Android anahtarı güvenli kaydedemedi. Keystore desteğini kontrol et.");
            return;
        }
        cancelRequest();
        if (apiKey != null && !apiKey.equals(candidate)) {
            while (history.length() > 0) history.remove(history.length() - 1);
        }
        apiKey = candidate;
        editingKey = false;
        manualKey.setText("");
        updateSetupVisibility();
        setStatus("Gemini anahtarı kaydedildi. Mikrofon başlatılıyor…");
        maybeGreet();
        ensureMicPermission();
    }

    private void chooseKeyFile() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("*/*");
        try { startActivityForResult(intent, OPEN_KEY_FILE); }
        catch (ActivityNotFoundException | SecurityException ex) {
            setStatus("Android dosya seçicisi yok. Alttaki gizli anahtar alanına Gemini API anahtarını bir kez gir.");
            if (manualKey != null) manualKey.requestFocus();
        }
    }

    private void configureTts() {
        tts = new TextToSpeech(this, result -> ui.post(() -> {
            if (destroyed) return;
            if (result == TextToSpeech.SUCCESS && tts != null) {
                int language = tts.setLanguage(Locale.forLanguageTag("tr-TR"));
                ttsReady = language != TextToSpeech.LANG_MISSING_DATA
                        && language != TextToSpeech.LANG_NOT_SUPPORTED;
                if (ttsReady) {
                    tts.setSpeechRate(1.04f);
                    tts.setPitch(0.96f);
                    tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                        @Override public void onStart(String id) { }
                        @Override public void onDone(String id) { finishSpeech(id, false); }
                        @Override public void onError(String id) { finishSpeech(id, true); }
                        @Override public void onStop(String id, boolean interrupted) {
                            finishSpeech(id, false);
                        }
                    });
                }
            }
            if (!ttsReady && apiKey != null && !sleeping) setStatus("Türkçe TTS bulunamadı. Yazılı yanıt ve varsa mikrofon kullanılabilir.");
            maybeGreet();
        }));
    }

    private void maybeGreet() {
        if (!foreground || apiKey == null || greetingPlayed || sleeping || !voiceEnabled) return;
        if (ttsReady) {
            greetingPlayed = true;
            say("Merhaba. Ben JARVIS. Seni dinliyorum.");
        }
    }

    private void finishSpeech(String id, boolean failed) {
        ui.post(() -> {
            if (destroyed || !id.equals(activeUtterance)) return;
            ui.removeCallbacks(speechTimeout);
            activeUtterance = null;
            speaking = false;
            if (failed) setStatus("Android Türkçe ses motoru ses çıkaramadı.");
            scheduleListen(300);
        });
    }

    private void stopSpeech() {
        ui.removeCallbacks(speechTimeout);
        activeUtterance = null;
        speaking = false;
        if (tts != null) {
            try { tts.stop(); } catch (RuntimeException ignored) { }
        }
    }

    private void onSpeechTimeout() {
        stopSpeech();
        setStatus("Seslendirme zaman aşımına uğradı. Yazılı yanıt ekranda.");
        scheduleListen(300);
    }

    private void say(String message) {
        if (!foreground || sleeping || !voiceEnabled || !ttsReady || tts == null) return;
        ui.removeCallbacks(speechTimeout);
        String utteranceId = Long.toString(++utteranceSequence);
        activeUtterance = utteranceId;
        try {
            speaking = true;
            int queued = tts.speak(message, TextToSpeech.QUEUE_FLUSH, null, utteranceId);
            if (queued == TextToSpeech.ERROR) {
                activeUtterance = null;
                speaking = false;
                setStatus("Türkçe seslendirme başarısız. Android TTS kurulumunu kontrol et.");
            } else {
                long speechLimit = Math.max(12000L, message.length() * 140L);
                ui.postDelayed(speechTimeout, speechLimit);
            }
        } catch (RuntimeException ex) {
            activeUtterance = null;
            speaking = false;
            setStatus("Android ses motoru çalışmadı.");
        }
    }

    private void releaseRecognizer() {
        listening = false;
        ui.removeCallbacks(microphoneTimeout);
        SpeechRecognizer previous = recognizer;
        recognizer = null;
        if (previous != null) {
            try { previous.cancel(); } catch (RuntimeException ignored) { }
            try { previous.destroy(); } catch (RuntimeException ignored) { }
        }
        setMic("● MİKROFON KAPALI");
    }

    private void scheduleListen(long waitMs) {
        ui.removeCallbacks(nextListen);
        if (!foreground || destroyed || manualKey.hasFocus() || recognitionBlocked || listening) return;
        ui.postDelayed(nextListen, waitMs);
    }

    private void ensureMicPermission() {
        if (!foreground || destroyed || manualKey.hasFocus()) return;
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            if (apiKey != null) setStatus("JARVIS'in seni duyabilmesi için Android mikrofon izni gerekiyor.");
            setMic("● MİKROFON İZNİ GEREKİYOR");
            if (!permissionRequested) {
                permissionRequested = true;
                requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, MIC_PERMISSION);
            }
            return;
        }
        scheduleListen(400);
    }

    @Override public void onRequestPermissionsResult(int request,
            String[] permissions, int[] grants) {
        super.onRequestPermissionsResult(request, permissions, grants);
        if (request != MIC_PERMISSION) return;
        if (grants.length > 0 && grants[0] == PackageManager.PERMISSION_GRANTED) {
            if (sleeping) showSleepStatus();
            else if (apiKey != null) setStatus("Mikrofon izni verildi. JARVIS dinlemeye başlıyor.");
            scheduleListen(300);
        } else {
            setMic("● MİKROFON İZNİ VERİLMEDİ");
            setStatus("Mikrofon izni reddedildi. Android Uygulama Ayarları'ndan izin ver; yazılı sohbet kullanılabilir.");
        }
    }

    private void startRecognition() {
        if (!foreground || destroyed || manualKey.hasFocus() || listening || recognitionBlocked) return;
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) return;
        try {
            if (!SpeechRecognizer.isRecognitionAvailable(this)) {
                recognitionBlocked = true;
                setMic("● KONUŞMA TANIMA HİZMETİ YOK");
                setStatus("Bu cihazda Android konuşma tanıma hizmeti bulunamadı. "
                        + "Uyumlu mikrofon ve konuşma tanıma servisi gerekir.");
                return;
            }
            SpeechRecognizer session = SpeechRecognizer.createSpeechRecognizer(this);
            recognizer = session;
            session.setRecognitionListener(new RecognitionListener() {
                private boolean isCurrent() {
                    return foreground && listening && recognizer == session;
                }

                @Override public void onReadyForSpeech(Bundle params) {
                    if (isCurrent()) {
                        setMic(sleeping ? "● UYKU MODU · JARVIS UYAN" : "● DİNLİYOR · KONUŞABİLİRSİN");
                    }
                }
                @Override public void onBeginningOfSpeech() {
                    if (isCurrent() && !sleeping) setMic("● SES ALGILANDI");
                }
                @Override public void onRmsChanged(float rms) { }
                @Override public void onBufferReceived(byte[] b) { }
                @Override public void onEndOfSpeech() {
                    if (isCurrent() && !sleeping) setMic("● KONUŞMA İŞLENİYOR");
                }
                @Override public void onError(int code) {
                    if (isCurrent()) speechError(code);
                }
                @Override public void onResults(Bundle results) {
                    if (!isCurrent()) return;
                    ArrayList<String> words = results.getStringArrayList(
                            SpeechRecognizer.RESULTS_RECOGNITION);
                    releaseRecognizer();
                    serviceFailures = 0;
                    if (words != null && !words.isEmpty()) {
                        handleUtterance(words.get(0), true);
                    }
                    scheduleListen(500);
                }
                @Override public void onPartialResults(Bundle result) { }
                @Override public void onEvent(int eventType, Bundle data) { }
            });
            Intent request = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
            request.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                    RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
            request.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "tr-TR");
            request.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
            listening = true;
            setMic("● MİKROFON AÇILIYOR");
            ui.postDelayed(microphoneTimeout, SESSION_TIMEOUT_MS);
            session.startListening(request);
        } catch (RuntimeException ex) {
            releaseRecognizer();
            retrySpeech("Android konuşma tanıma hizmeti başlatılamadı.");
        }
    }

    private void speechError(int code) {
        releaseRecognizer();
        if (code == SpeechRecognizer.ERROR_NO_MATCH
                || code == SpeechRecognizer.ERROR_SPEECH_TIMEOUT) {
            serviceFailures = 0;
            scheduleListen(550);
            return;
        }
        if (code == SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS) {
            recognitionBlocked = true;
            setMic("● MİKROFON İZNİ GEREKİYOR");
            setStatus("Mikrofon izni eksik. Android uygulama ayarlarını kontrol et.");
            return;
        }
        retrySpeech("Android konuşma tanıma hatası (" + code + ").");
    }

    private void retrySpeech(String message) {
        serviceFailures = Math.min(serviceFailures + 1, MAX_SERVICE_FAILURES);
        setMic("● SES TANIMA YENİDEN DENENECEK");
        setStatus(message + " Yazılı giriş kullanılabilir.");
        scheduleListen(1000L << (serviceFailures - 1));
    }

    private void showSleepStatus() {
        setStatus("UYKU MODU · Devam etmek için ‘JARVIS uyan’ de veya yaz.");
        if (listening) setMic("● UYKU MODU · JARVIS UYAN");
    }

    private void handleUtterance(String utterance, boolean fromMicrophone) {
        if (utterance == null || utterance.trim().isEmpty()) return;
        VoiceControl.Command command = VoiceControl.classify(utterance);
        if (command == VoiceControl.Command.SLEEP) {
            sleeping = true;
            cancelRequest();
            stopSpeech();
            showSleepStatus();
            return;
        }
        if (command == VoiceControl.Command.WAKE) {
            boolean wasSleeping = sleeping;
            sleeping = false;
            setStatus("JARVIS hazır.");
            if (listening) setMic("● DİNLİYOR · KONUŞABİLİRSİN");
            if (wasSleeping) {
                greetingPlayed = true;
                say("Dinliyorum.");
            }
            return;
        }
        if (sleeping) {
            if (!fromMicrophone) showSleepStatus();
            return;
        }
        if (command == VoiceControl.Command.MUTE) {
            voiceEnabled = false;
            stopSpeech();
            setStatus("SESSİZ MOD · ‘Konuş’ dersen sesli yanıtı açarım.");
            return;
        }
        if (command == VoiceControl.Command.UNMUTE) {
            boolean changed = !voiceEnabled;
            voiceEnabled = true;
            setStatus("SESLİ MOD · JARVIS konuşmaya hazır.");
            if (changed) say("Dinliyorum.");
            return;
        }
        if (fromMicrophone && speaking) return;
        DeviceCommand local = DeviceCommand.parse(utterance);
        if (local != null) {
            if (!fromMicrophone) prompt.setText("");
            if (local.leavesJarvis()) {
                cancelRequest();
                stopSpeech();
            }
            try {
                setStatus(DeviceActions.execute(this, local));
            } catch (SecurityException denied) {
                setStatus("Android bu cihaz komutuna izin vermedi.");
            }
            return;
        }
        if (activeRequest != null) {
            setStatus("Önceki istek henüz tamamlanmadı.");
            return;
        }
        sendMessage(utterance);
    }

    private void append(String sender, String value) {
        String next = conversation.getText().toString() + "\n" + sender + ": " + value + "\n";
        if (next.length() > 16000) next = next.substring(next.length() - 16000);
        conversation.setText(next);
    }

    private void sendMessage(String input) {
        if (apiKey == null) {
            setStatus("Önce Gemini API anahtarını gir veya anahtar dosyasını seç.");
            return;
        }
        if (editingKey) {
            setStatus("Devam etmek için yeni Gemini anahtarını kaydet.");
            return;
        }
        if (activeRequest != null || input == null || input.trim().isEmpty()) return;
        String question = input.trim();
        if (question.length() > 2000) {
            setStatus("Soru en fazla 2000 karakter olabilir.");
            return;
        }
        String selected = String.valueOf(model.getSelectedItem());
        if (!GeminiHttp.allowedModel(selected)) {
            setStatus("Seçilen Gemini modeli desteklenmiyor.");
            return;
        }
        final String keyForCall = apiKey;
        final JSONArray past;
        try {
            past = new JSONArray(history.toString());
        } catch (Exception ignored) {
            setStatus("Sohbet geçmişi hazırlanamadı. Tekrar dene.");
            return;
        }

        GeminiHttp.Call request = new GeminiHttp.Call();
        activeRequest = request;
        try {
            activeTask = worker.submit(() -> {
                try {
                    String answer = GeminiHttp.ask(request, keyForCall, selected, past, question);
                    ui.post(() -> showAnswer(request, question, selected, answer));
                } catch (Exception ex) {
                    ui.post(() -> showRequestError(request, ex));
                }
            });
        } catch (RejectedExecutionException ex) {
            activeRequest = null;
            setStatus("Önceki bağlantı kapanıyor. Birkaç saniye sonra tekrar dene.");
            return;
        }
        prompt.setText("");
        append("SEN", question);
        setStatus("Gemini yanıtlıyor…");
        ui.postDelayed(requestTimeout, 40000L);
    }

    private boolean finishRequest(GeminiHttp.Call request) {
        if (destroyed || activeRequest != request) return false;
        activeRequest = null;
        activeTask = null;
        ui.removeCallbacks(requestTimeout);
        return true;
    }

    private void cancelRequest() {
        if (activeRequest == null) return;
        HttpURLConnection connection = activeRequest.cancel();
        Future<?> task = activeTask;
        finishRequest(activeRequest);
        if (task != null) task.cancel(true);
        if (connection != null) {
            new Thread(() -> {
                try { connection.disconnect(); } catch (RuntimeException ignored) { }
            }, "gemini-disconnect").start();
        }
    }

    private void onRequestTimeout() {
        cancelRequest();
        setStatus("Gemini yanıtı zaman aşımına uğradı. Tekrar sorabilirsin.");
    }

    private void showAnswer(GeminiHttp.Call request, String question, String modelName, String answer) {
        if (!finishRequest(request)) return;
        try {
            history.put(new JSONObject().put("role", "user").put("text", question));
            history.put(new JSONObject().put("role", "model").put("text", answer));
            while (history.length() > 8) history.remove(0);
        } catch (Exception ignored) { }
        replaceKey.setVisibility(android.view.View.GONE);
        append("JARVIS", answer);
        setStatus("Gemini yanıtladı · " + modelName);
        say(answer.substring(0, Math.min(answer.length(), 3000)));
    }

    private void showRequestError(GeminiHttp.Call request, Exception error) {
        if (!finishRequest(request)) return;
        String message = "Gemini bağlantısı kesildi. İnterneti kontrol edip tekrar dene.";
        if (error instanceof GeminiHttp.ApiError) {
            GeminiHttp.ApiError apiError = (GeminiHttp.ApiError) error;
            message = apiError.getMessage();
            if (apiError.canReplaceKey()) replaceKey.setVisibility(android.view.View.VISIBLE);
        } else if (error instanceof SocketTimeoutException) {
            message = "Gemini yanıtı zaman aşımına uğradı. Tekrar sorabilirsin.";
        } else if (error instanceof UnknownHostException) {
            message = "Gemini'ye ulaşılamadı. Wi-Fi bağlantısını kontrol et.";
        } else if (error instanceof org.json.JSONException) {
            message = "Gemini yanıtı okunamadı. Tekrar dene.";
        }
        setStatus(message);
    }

    private static String readBounded(InputStream input, int limit) throws Exception {
        ByteArrayOutputStream result = new ByteArrayOutputStream();
        byte[] buf = new byte[1024];
        int read;
        while ((read = input.read(buf)) != -1) {
            if (result.size() + read > limit) throw new Exception("Too large");
            result.write(buf, 0, read);
        }
        return new String(result.toByteArray(), StandardCharsets.UTF_8);
    }

    @Override protected void onActivityResult(int request, int result, Intent intent) {
        super.onActivityResult(request, result, intent);
        if (request != OPEN_KEY_FILE || result != RESULT_OK
                || intent == null || intent.getData() == null) return;
        if (apiKey != null && !editingKey) return;
        String imported;
        try (InputStream stream = getContentResolver().openInputStream(intent.getData())) {
            if (stream == null) throw new Exception("Missing file");
            JSONObject file = new JSONObject(readBounded(stream, 4096));
            imported = file.optString("api_key", "");
            if (file.length() != 3 || file.optInt("version") != 2
                    || !"gemini".equals(file.optString("provider"))
                    || !imported.matches("[\\x21-\\x7e]{20,220}")) {
                throw new Exception("Invalid key file");
            }
        } catch (Exception e) {
            setStatus("Anahtar dosyası okunamadı. JSON dosyasını kontrol et veya anahtarı elle gir.");
            return;
        }
        saveKey(imported);
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        state.putBoolean("sleeping", sleeping);
        state.putBoolean("voiceEnabled", voiceEnabled);
        state.putBoolean("permissionRequested", permissionRequested);
        state.putBoolean("editingKey", editingKey);
    }

    @Override protected void onResume() {
        super.onResume();
        foreground = true;
        recognitionBlocked = false;
        serviceFailures = 0;
        maybeGreet();
        ensureMicPermission();
    }

    @Override protected void onStop() {
        foreground = false;
        if (activeRequest != null) {
            cancelRequest();
            setStatus("Uygulama arka plana geçtiği için Gemini isteği durduruldu.");
        }
        ui.removeCallbacks(nextListen);
        releaseRecognizer();
        stopSpeech();
        super.onStop();
    }

    @Override protected void onDestroy() {
        cancelRequest();
        destroyed = true;
        ui.removeCallbacks(nextListen);
        ui.removeCallbacks(microphoneTimeout);
        releaseRecognizer();
        if (tts != null) { tts.stop(); tts.shutdown(); }
        apiKey = null;
        worker.shutdownNow();
        super.onDestroy();
    }
}
