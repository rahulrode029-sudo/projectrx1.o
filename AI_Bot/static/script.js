import { GoogleGenAI, Modality } from "https://esm.run/@google/genai";


// =====================================================
// SAFE DOM HELPERS
//
// Never build messages with innerHTML: both the user
// message and the model reply are untrusted content and
// must be inserted as text, never as markup.
// =====================================================

function appendMessage(className, label, text) {

    const chatBox = document.getElementById("chat-box");

    const wrapper = document.createElement("div");
    wrapper.className = "message " + className;

    const strong = document.createElement("strong");
    strong.textContent = label;

    const paragraph = document.createElement("p");
    paragraph.textContent = text;

    wrapper.appendChild(strong);
    wrapper.appendChild(paragraph);

    chatBox.appendChild(wrapper);

    chatBox.scrollTop = chatBox.scrollHeight;

}


// =====================================================
// CHAT MODE
// =====================================================

async function sendMessage() {

    const input = document.getElementById("message");

    const message = input.value.trim();

    if (!message) {
        return;
    }

    appendMessage("user", "You:", message);

    input.value = "";

    try {

        const response = await fetch("/chat", {
            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                message: message
            })
        });

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        if (typeof data.response !== "string") {
            throw new Error("Empty response from the server.");
        }

        appendMessage("bot", "AI Bot:", data.response);

    } catch (error) {

        appendMessage(
            "bot",
            "Error:",
            error && error.message ? error.message : "Something went wrong."
        );

    }
}


// Press Enter to send
document.getElementById("message").addEventListener(
    "keydown",
    function(event) {

        if (event.key === "Enter") {
            sendMessage();
        }

    }
);


// =====================================================
// VOICE VARIABLES
// =====================================================

let voiceSession = null;
let audioContext = null;
let mediaStream = null;
let processor = null;

let audioQueue = [];
let isPlayingAudio = false;


// =====================================================
// ELEMENTS
// =====================================================

const chatMode = document.getElementById("chat-mode");
const voiceMode = document.getElementById("voice-mode");

const voicePanel = document.getElementById("voice-panel");

const startVoice = document.getElementById("start-voice");
const stopVoice = document.getElementById("stop-voice");

const voiceStatus = document.getElementById("voice-status");


// =====================================================
// MODE SWITCHING
// =====================================================

chatMode.addEventListener("click", () => {

    voicePanel.style.display = "none";

});


voiceMode.addEventListener("click", () => {

    voicePanel.style.display = "block";

});


// =====================================================
// START VOICE
// =====================================================

startVoice.addEventListener(
    "click",
    startVoiceChat
);


async function startVoiceChat() {

    try {

        voiceStatus.textContent =
            "Getting voice token...";


        // ---------------------------------------------
        // GET TEMPORARY TOKEN FROM FLASK
        // ---------------------------------------------

        const tokenResponse = await fetch(
            "/voice-token",
            {
                method: "POST"
            }
        );


        const tokenData =
            await tokenResponse.json();


        if (!tokenResponse.ok || tokenData.error) {

            throw new Error(
                tokenData.error ||
                "Could not create voice token"
            );

        }


        const token =
            tokenData.token;


        console.log(
            "Temporary token received"
        );


        voiceStatus.textContent =
            "Connecting to Gemini...";


        // ---------------------------------------------
        // CREATE GEMINI CLIENT
        // ---------------------------------------------

        const ai = new GoogleGenAI({
            apiKey: token,

            httpOptions: {
                apiVersion: "v1alpha"
            }
        });


        // ---------------------------------------------
        // CONNECT TO GEMINI LIVE
        // ---------------------------------------------

        voiceSession = await ai.live.connect({

            model:
                "gemini-3.1-flash-live-preview",


            config: {

                responseModalities: [
                    Modality.AUDIO
                ],

                systemInstruction:
                    "You are a helpful AI assistant. " +
                    "Talk naturally with the user. " +
                    "Give clear and useful answers."

            },


            callbacks: {

                onopen: () => {

                    console.log(
                        "Gemini Live connected"
                    );

                    voiceStatus.textContent =
                        "Listening... Speak now.";

                },


                onmessage: async (message) => {

                    console.log(
                        "Gemini response:",
                        message
                    );

                    await handleGeminiAudio(
                        message
                    );

                },


                onerror: (error) => {

                    console.error(
                        "Gemini Live error:",
                        error
                    );

                    voiceStatus.textContent =
                        "Voice connection error.";

                },


                onclose: () => {

                    console.log(
                        "Gemini Live connection closed"
                    );

                    voiceStatus.textContent =
                        "Voice connection closed.";

                }

            }

        });


        // ---------------------------------------------
        // START MICROPHONE
        // ---------------------------------------------

        await startMicrophone();


        startVoice.disabled = true;
        stopVoice.disabled = false;


    } catch (error) {

        console.error(
            "Voice error:",
            error
        );

        voiceStatus.textContent =
            "Voice error: " +
            error.message;

    }

}


// =====================================================
// MICROPHONE
// =====================================================

async function startMicrophone() {

    mediaStream =
        await navigator.mediaDevices.getUserMedia({
            audio: true
        });


    audioContext =
        new AudioContext({
            sampleRate: 16000
        });


    const source =
        audioContext.createMediaStreamSource(
            mediaStream
        );


    processor =
        audioContext.createScriptProcessor(
            2048,
            1,
            1
        );


    processor.onaudioprocess =
        function(event) {

            if (!voiceSession) {
                return;
            }


            const inputData =
                event.inputBuffer
                    .getChannelData(0);


            const pcmData =
                convertFloat32ToPCM(
                    inputData
                );


            const base64Audio =
                arrayBufferToBase64(
                    pcmData
                );


            voiceSession.sendRealtimeInput({

                audio: {

                    data: base64Audio,

                    mimeType:
                        "audio/pcm;rate=16000"

                }

            });

        };


    source.connect(processor);

    processor.connect(
        audioContext.destination
    );

}


// =====================================================
// FLOAT32 → PCM16
// =====================================================

function convertFloat32ToPCM(
    float32Array
) {

    const buffer =
        new ArrayBuffer(
            float32Array.length * 2
        );


    const view =
        new DataView(buffer);


    for (
        let i = 0;
        i < float32Array.length;
        i++
    ) {

        let sample =
            Math.max(
                -1,
                Math.min(
                    1,
                    float32Array[i]
                )
            );


        view.setInt16(

            i * 2,

            sample < 0
                ? sample * 0x8000
                : sample * 0x7fff,

            true

        );

    }


    return buffer;

}


// =====================================================
// ARRAY BUFFER → BASE64
// =====================================================

function arrayBufferToBase64(
    buffer
) {

    let binary = "";

    const bytes =
        new Uint8Array(buffer);


    for (
        let i = 0;
        i < bytes.length;
        i++
    ) {

        binary += String.fromCharCode(
            bytes[i]
        );

    }


    return btoa(binary);

}


// =====================================================
// HANDLE GEMINI AUDIO
// =====================================================

async function handleGeminiAudio(
    message
) {

    try {

        const parts =
            message.serverContent
                ?.modelTurn
                ?.parts;


        if (!parts) {
            return;
        }


        for (const part of parts) {

            if (
                part.inlineData &&
                part.inlineData.data
            ) {

                const audioData =
                    base64ToArrayBuffer(
                        part.inlineData.data
                    );


                await playPCM(
                    audioData
                );

            }

        }

    } catch (error) {

        console.error(
            "Audio playback error:",
            error
        );

    }

}


// =====================================================
// BASE64 → ARRAY BUFFER
// =====================================================

function base64ToArrayBuffer(
    base64
) {

    const binary =
        atob(base64);


    const bytes =
        new Uint8Array(
            binary.length
        );


    for (
        let i = 0;
        i < binary.length;
        i++
    ) {

        bytes[i] =
            binary.charCodeAt(i);

    }


    return bytes.buffer;

}


// =====================================================
// PLAY GEMINI AUDIO
// =====================================================

async function playPCM(buffer) {

    if (!audioContext) {
        return;
    }

    const int16 = new Int16Array(buffer);

    const audioBuffer = audioContext.createBuffer(
        1,
        int16.length,
        24000
    );

    const channelData =
        audioBuffer.getChannelData(0);

    for (let i = 0; i < int16.length; i++) {
        channelData[i] =
            int16[i] / 32768;
    }

    audioQueue.push(audioBuffer);

    if (!isPlayingAudio) {
        playNextAudio();
    }
}

// =====================================================
// STOP VOICE
// =====================================================

stopVoice.addEventListener(
    "click",
    stopVoiceChat
);


function stopVoiceChat() {


    // Stop microphone
    if (mediaStream) {

        mediaStream
            .getTracks()
            .forEach(
                track => track.stop()
            );

        mediaStream = null;

    }


    // Stop processor
    if (processor) {

        processor.disconnect();

        processor = null;

    }


    // Close audio
    if (audioContext) {

        audioContext.close();

        audioContext = null;

    }


    // Close Gemini session
    if (voiceSession) {

        voiceSession.close();

        voiceSession = null;

    }


    startVoice.disabled = false;

    stopVoice.disabled = true;


    voiceStatus.textContent =
        "Voice stopped.";

}

async function playNextAudio() {

    if (audioQueue.length === 0) {

        isPlayingAudio = false;

        return;
    }

    isPlayingAudio = true;

    const audioBuffer =
        audioQueue.shift();

    const source =
        audioContext.createBufferSource();

    source.buffer = audioBuffer;

    source.connect(
        audioContext.destination
    );

    source.onended = () => {

        playNextAudio();

    };

    source.start();
}