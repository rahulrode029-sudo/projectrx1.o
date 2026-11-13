// =====================================================
// SAFE DOM HELPERS
//
// Both the user message and the model reply are untrusted
// content, so they are inserted as text, never as markup.
// =====================================================

function appendMessage(className, label, text) {

    const chatBox = document.getElementById("chat-box");

    const wrapper = document.createElement("div");
    wrapper.className = className;

    const bold = document.createElement("b");
    bold.textContent = label;

    wrapper.appendChild(bold);
    wrapper.appendChild(document.createTextNode(" " + text));

    chatBox.appendChild(wrapper);

    chatBox.scrollTop = chatBox.scrollHeight;

}


async function sendMessage() {

    const input = document.getElementById("message");

    const message = input.value.trim();

    if (!message) {
        return;
    }

    appendMessage("user-message", "You:", message);

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

        appendMessage("bot-message", "Bot:", data.response);

    } catch (error) {

        appendMessage(
            "bot-message",
            "Error:",
            error && error.message ? error.message : "Something went wrong."
        );

    }
}
