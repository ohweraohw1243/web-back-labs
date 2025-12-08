from flask import Blueprint, render_template, request, session, jsonify
import random

lab9 = Blueprint('lab9', __name__)

PREMIUM_BOXES = {7, 8, 9}  

if not hasattr(lab9, "boxes"):
    lab9.boxes = []
    for i in range(10):
        lab9.boxes.append({
            "id": i,
            "x": random.randint(50, 900),
            "y": random.randint(120, 500),
            "opened": False,
            "box_img": f"/static/lab9/box{i+1}.jpg",
            "gift_img": f"/static/lab9/gift{i+1}.jpg",
            "text": f"Поздравление №{i+1}! С Новым годом и счастьем!"
        })

@lab9.route("/lab9/")
def lab():
    session.setdefault("opened_count", 0)
    return render_template("lab9/index.html",
                           logged_in="login" in session)


@lab9.route("/lab9/api/boxes", methods=["POST"])
def get_boxes():
    remaining = len([b for b in lab9.boxes if not b["opened"]])
    logged_in = "login" in session

    return jsonify({
        "boxes": [
            {
                "id": b["id"],
                "x": b["x"],
                "y": b["y"],
                "opened": b["opened"],
                "box_img": b["box_img"],
                "gift_img": b["gift_img"],      
                "text": b["text"],             
                "premium": (b["id"] in PREMIUM_BOXES)
            }
            for b in lab9.boxes
        ],
        "remaining": remaining,
        "logged_in": logged_in
    })


@lab9.route("/lab9/api/open", methods=["POST"])
def open_box():
    data = request.json
    box_id = data["id"]

    if box_id in PREMIUM_BOXES and "login" not in session:
        return jsonify({"error": "Этот подарок доступен только авторизованным пользователям!"})

    if session.get("opened_count", 0) >= 3:
        return jsonify({"error": "Можно открыть только 3 подарка!"})

    box = lab9.boxes[box_id]

    if box["opened"]:
        return jsonify({"error": "Коробка уже открыта!"})

    box["opened"] = True
    session["opened_count"] += 1

    return jsonify({
        "text": box["text"],
        "gift": box["gift_img"]
    })


@lab9.route("/lab9/api/reset", methods=["POST"])
def reset_boxes():
    """Доступно только авторизованным пользователям"""
    if "login" not in session:
        return jsonify({"error": "Только Дед Мороз может перезаполнить коробки!"})

    for box in lab9.boxes:
        box["opened"] = False

    session["opened_count"] = 0

    return jsonify({"result": "ok"})
