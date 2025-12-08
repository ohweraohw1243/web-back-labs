function loadBoxes() {
    fetch("/lab9/api/boxes", { method: "POST" })
        .then(r => r.json())
        .then(data => {
            let field = document.getElementById("field");
            field.innerHTML = "";

            document.getElementById("remaining").innerText = data.remaining;

            if (data.logged_in) {
                const santa = document.getElementById("santa");
                if (santa) {
                    santa.onclick = resetBoxes;
                }
            }

            data.boxes.forEach(b => {
                let img = document.createElement("img");

                img.src = b.opened ? b.gift_img : b.box_img;
                img.style.position = "absolute";
                img.style.left = b.x + "px";
                img.style.top = b.y + "px";
                img.style.width = "130px";
                img.style.cursor = "pointer";

                img.onclick = () => openBox(b.id, img);

                field.append(img);
            });
        });
}


function openBox(id, imgElement) {
    fetch("/lab9/api/open", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id })
    })
        .then(r => r.json())
        .then(data => {
            const msg = document.getElementById("message");

            if (data.error) {
                msg.innerText = data.error;
                return;
            }

            imgElement.src = data.gift;
            msg.innerText = data.text;

            loadBoxes();
        });
}


function resetBoxes() {
    fetch("/lab9/api/reset", { method: "POST" })
        .then(r => r.json())
        .then(() => loadBoxes());
}


window.onload = loadBoxes;
