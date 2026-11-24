from flask import Flask, abort, redirect, render_template, request, url_for
from flask_login import current_user
from stock_manager.models import Actor
from services.catalogue import Catalogue, CatalogueError
from stock_manager.auth import configure_auth, admin_required

app = Flask(__name__)
catalogue = Catalogue()
configure_auth(app)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/inventory")
def inventory():
    search = request.args.get("search", "").strip()
    selected = list(dict.fromkeys(request.args.getlist("category")))
    mode = request.args.get("match", "any")
    if mode not in {"any", "all"}:
        mode = "any"
    status = request.args.get("status", "")
    if status not in {"", "available", "low", "out"}:
        status = ""
    filtered = catalogue.filter_products(search, selected, mode, status)
    return render_template("inventory.html", products=catalogue.product_rows(filtered),
                           categories=catalogue.sorted_categories(), search=search,
                           selected_categories=selected, match_mode=mode,
                           selected_status=status, **catalogue.statistics())


@app.route("/admin")
@admin_required
def admin():
    return render_template("admin.html", products=catalogue.product_rows())


def render_product_form(template, product=None, error=None, status=200):
    if request.method == "POST":
        values = {"name": request.form.get("name", ""),
                  "category_ids": request.form.getlist("category_ids"),
                  "quantity": product["quantity"] if product else request.form.get("quantity", ""),
                  "min_stock": request.form.get("min_stock", ""),
                  "price": request.form.get("price", "")}
    else:
        values = product or {"name": "", "category_ids": [], "quantity": 0, "min_stock": 0, "price": ""}
    return render_template(template, product=product, values=values,
                           categories=catalogue.sorted_categories(), error=error), status


@app.route("/admin/add", methods=["GET", "POST"])
@admin_required
def add_product():
    if request.method == "POST":
        try:
            catalogue.add_product(request.form.get("name", ""), request.form.getlist("category_ids"),
                                  request.form.get("quantity", ""), request.form.get("min_stock", ""),
                                  request.form.get("price", ""),
                                  actor=Actor(str(current_user.id), current_user.username))
        except CatalogueError as error:
            return render_product_form("add_product.html", error=str(error), status=400)
        return redirect(url_for("admin"), code=303)
    return render_product_form("add_product.html")


@app.route("/admin/edit/<product_id>", methods=["GET", "POST"])
@admin_required
def edit_product(product_id):
    product = catalogue.get_product(product_id)
    if product is None:
        abort(404)
    if request.method == "POST":
        try:
            catalogue.edit_product(product_id, request.form.get("name", ""), request.form.getlist("category_ids"),
                                   request.form.get("min_stock", ""), request.form.get("price", ""))
        except CatalogueError as error:
            return render_product_form("edit_product.html", product, str(error), 400)
        return redirect(url_for("admin"), code=303)
    return render_product_form("edit_product.html", product)


def render_categories(edit=None, name="", error=None, status=200):
    return render_template("categories.html", categories=catalogue.category_rows(),
                           classified_count=sum(bool(p["category_ids"]) for p in catalogue.products),
                           editing=edit, name=name, error=error), status


@app.route("/admin/categories", methods=["GET", "POST"])
@admin_required
def manage_categories():
    if request.method == "POST":
        name = request.form.get("name", "")
        try:
            catalogue.add_category(name)
        except CatalogueError as error:
            return render_categories(name=name, error=str(error), status=400)
        return redirect(url_for("manage_categories"), code=303)
    edit_id = request.args.get("edit")
    edit = catalogue.get_category(edit_id) if edit_id else None
    if edit_id and edit is None:
        abort(404)
    return render_categories(edit=edit, name=edit["name"] if edit else "")


@app.post("/admin/categories/<category_id>/rename")
@admin_required
def rename_category(category_id):
    category = catalogue.get_category(category_id)
    if category is None:
        abort(404)
    name = request.form.get("name", "")
    try:
        catalogue.rename_category(category_id, name)
    except CatalogueError as error:
        return render_categories(edit=category, name=name, error=str(error), status=400)
    return redirect(url_for("manage_categories"), code=303)


@app.post("/admin/categories/<category_id>/delete")
@admin_required
def delete_category(category_id):
    if catalogue.get_category(category_id) is None:
        abort(404)
    try:
        catalogue.delete_category(category_id)
    except CatalogueError as error:
        return render_categories(error=str(error), status=409)
    return redirect(url_for("manage_categories"), code=303)


# ---------------------------------------------------------------------------
# Phase 3.2: administrative stock operations and immutable audit views
# ---------------------------------------------------------------------------

def render_stock_form(product, error=None, status=200):
    """Re-render failed POSTs without discarding user-supplied form data."""
    if request.method == "POST":
        fields = {
            "kind": request.form.get("kind", "entry"),
            "amount": request.form.get("amount", ""),
            "reason": request.form.get("reason", ""),
        }
    else:
        fields = {"kind": "entry", "amount": "", "reason": ""}
    return render_template("stock_movement.html", product=product,
                           fields=fields, error=error), status


@app.route("/admin/stock/<product_id>", methods=["GET", "POST"])
@admin_required
def stock_operation(product_id):
    product = catalogue.get_product(product_id)
    if product is None:
        abort(404)
    if request.method == "POST":
        try:
            catalogue.record_stock_movement(
                product_code=product_id,
                kind=request.form.get("kind", ""),
                amount=request.form.get("amount", ""),
                reason=request.form.get("reason", ""),
                expected_quantity=request.form.get("expected_quantity"),
                actor=Actor(str(current_user.id), current_user.username),
            )
        except CatalogueError as error:
            # The stock displayed on the page might have changed between the
            # initial GET and the POST; always fetch the new current balance.
            return render_stock_form(catalogue.get_product(product_id), str(error), 400)
        return redirect(url_for("stock_history", product_id=product_id), code=303)
    return render_stock_form(product)


@app.get("/admin/stock/<product_id>/history")
@admin_required
def stock_history(product_id):
    product = catalogue.get_product(product_id, include_archived=True)
    if product is None:
        abort(404)
    return render_template("stock_history.html", product=product,
                           movements=catalogue.movement_rows(product_id))


@app.get("/admin/movements")
@admin_required
def all_movements():
    product_code = request.args.get("product", "").strip()
    if product_code and catalogue.get_product(product_code, include_archived=True) is None:
        abort(404)
    return render_template("movements.html", movements=catalogue.movement_rows(product_code or None),
                           products=catalogue.audit_product_rows(), selected_product=product_code)
