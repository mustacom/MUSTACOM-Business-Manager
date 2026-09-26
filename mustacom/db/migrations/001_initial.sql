-- ============================================================================
-- MUSTACOM BUSINESS MANAGER - initial schema (version 1)
-- Normalised SQLite schema. Money is stored as INTEGER centimes (x100),
-- quantities as INTEGER milli-units (x1000), percent rates as INTEGER x100.
-- Every transactional table carries created_at / updated_at / created_by.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- --------------------------------------------------------------------------
-- Security: roles, permissions, users
-- --------------------------------------------------------------------------
CREATE TABLE roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_system INTEGER NOT NULL DEFAULT 0,
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'active'
);

CREATE TABLE permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    action TEXT NOT NULL,
    UNIQUE (module, action)
);

CREATE TABLE role_permissions (
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE user_permissions (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    granted INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (user_id, permission_id)
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    email TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    role_id INTEGER REFERENCES roles(id),
    is_active INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    last_login_at TEXT,
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'active'
);

-- --------------------------------------------------------------------------
-- Catalogue: categories, brands, products, services
-- --------------------------------------------------------------------------
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    parent_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    kind TEXT NOT NULL DEFAULT 'product',   -- product | service | expense
    description TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'active'
);

CREATE TABLE brands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'active'
);

CREATE TABLE products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    barcode TEXT,
    name TEXT NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    subcategory_id INTEGER REFERENCES categories(id),
    brand_id INTEGER REFERENCES brands(id),
    reference TEXT DEFAULT '',
    unit TEXT NOT NULL DEFAULT 'u',
    purchase_price_cents INTEGER NOT NULL DEFAULT 0,
    sale_price_cents INTEGER NOT NULL DEFAULT 0,
    vat_rate_bp INTEGER NOT NULL DEFAULT 2000,
    price_includes_vat INTEGER NOT NULL DEFAULT 0,
    stock INTEGER NOT NULL DEFAULT 0,
    stock_min INTEGER NOT NULL DEFAULT 0,
    stock_max INTEGER NOT NULL DEFAULT 0,
    location TEXT DEFAULT '',
    supplier_id INTEGER REFERENCES suppliers(id),
    image_path TEXT DEFAULT '',
    description TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    track_stock INTEGER NOT NULL DEFAULT 1,
    sellable INTEGER NOT NULL DEFAULT 1,
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'active'
);
CREATE UNIQUE INDEX idx_products_barcode ON products(barcode)
    WHERE barcode IS NOT NULL AND barcode <> '';
CREATE INDEX idx_products_name ON products(name);
CREATE INDEX idx_products_category ON products(category_id);

-- --------------------------------------------------------------------------
-- Parties: customers, suppliers
-- --------------------------------------------------------------------------
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    company TEXT DEFAULT '',
    customer_type TEXT DEFAULT 'individual',
    address TEXT DEFAULT '',
    city TEXT DEFAULT '',
    zip TEXT DEFAULT '',
    country TEXT DEFAULT 'Maroc',
    phone TEXT DEFAULT '',
    mobile TEXT DEFAULT '',
    email TEXT DEFAULT '',
    ice TEXT DEFAULT '',
    if_number TEXT DEFAULT '',
    rc TEXT DEFAULT '',
    patente TEXT DEFAULT '',
    cnss TEXT DEFAULT '',
    credit_limit_cents INTEGER NOT NULL DEFAULT 0,
    balance_cents INTEGER NOT NULL DEFAULT 0,
    payment_terms TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'active'
);
CREATE INDEX idx_customers_name ON customers(name);

CREATE TABLE suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    contact_person TEXT DEFAULT '',
    address TEXT DEFAULT '',
    city TEXT DEFAULT '',
    zip TEXT DEFAULT '',
    country TEXT DEFAULT 'Maroc',
    phone TEXT DEFAULT '',
    mobile TEXT DEFAULT '',
    email TEXT DEFAULT '',
    ice TEXT DEFAULT '',
    if_number TEXT DEFAULT '',
    rc TEXT DEFAULT '',
    payment_terms TEXT DEFAULT '',
    balance_cents INTEGER NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'active'
);
CREATE INDEX idx_suppliers_name ON suppliers(name);

CREATE TABLE services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    category_id INTEGER REFERENCES categories(id),
    unit TEXT NOT NULL DEFAULT 'u',
    cost_cents INTEGER NOT NULL DEFAULT 0,
    price_cents INTEGER NOT NULL DEFAULT 0,
    vat_rate_bp INTEGER NOT NULL DEFAULT 2000,
    duration_minutes INTEGER DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'active'
);

-- --------------------------------------------------------------------------
-- Transport: vehicles, drivers
-- --------------------------------------------------------------------------
CREATE TABLE vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    registration TEXT DEFAULT '',
    capacity TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'active'
);

CREATE TABLE drivers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    license_number TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'active'
);

-- --------------------------------------------------------------------------
-- Document numbering
-- --------------------------------------------------------------------------
CREATE TABLE document_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type TEXT NOT NULL,
    year INTEGER NOT NULL,
    counter INTEGER NOT NULL DEFAULT 0,
    prefix TEXT DEFAULT '',
    UNIQUE (doc_type, year)
);

-- --------------------------------------------------------------------------
-- Point of sale
-- --------------------------------------------------------------------------
CREATE TABLE sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    customer_id INTEGER REFERENCES customers(id),
    cash_session_id INTEGER REFERENCES cash_sessions(id),
    invoice_id INTEGER REFERENCES invoices(id),
    source_type TEXT DEFAULT 'pos',
    source_id INTEGER,
    subtotal_cents INTEGER NOT NULL DEFAULT 0,
    discount_cents INTEGER NOT NULL DEFAULT 0,
    discount_percent_bp INTEGER NOT NULL DEFAULT 0,
    total_ht_cents INTEGER NOT NULL DEFAULT 0,
    total_vat_cents INTEGER NOT NULL DEFAULT 0,
    total_cents INTEGER NOT NULL DEFAULT 0,
    paid_cents INTEGER NOT NULL DEFAULT 0,
    change_cents INTEGER NOT NULL DEFAULT 0,
    payment_method TEXT DEFAULT 'cash',
    cost_cents INTEGER NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '',
    is_return INTEGER NOT NULL DEFAULT 0,
    parent_sale_id INTEGER REFERENCES sales(id),
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'validated'
);
CREATE INDEX idx_sales_date ON sales(date);
CREATE INDEX idx_sales_customer ON sales(customer_id);

CREATE TABLE sale_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    ref_type TEXT NOT NULL DEFAULT 'product',
    product_id INTEGER REFERENCES products(id),
    service_id INTEGER REFERENCES services(id),
    code TEXT DEFAULT '',
    label TEXT NOT NULL,
    unit TEXT DEFAULT 'u',
    quantity INTEGER NOT NULL DEFAULT 1000,
    unit_price_cents INTEGER NOT NULL DEFAULT 0,
    vat_rate_bp INTEGER NOT NULL DEFAULT 0,
    discount_percent_bp INTEGER NOT NULL DEFAULT 0,
    discount_cents INTEGER NOT NULL DEFAULT 0,
    line_ht_cents INTEGER NOT NULL DEFAULT 0,
    line_vat_cents INTEGER NOT NULL DEFAULT 0,
    line_total_cents INTEGER NOT NULL DEFAULT 0,
    cost_cents INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_sale_items_sale ON sale_items(sale_id);

CREATE TABLE sale_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    method TEXT NOT NULL DEFAULT 'cash',
    amount_cents INTEGER NOT NULL DEFAULT 0,
    reference TEXT DEFAULT '',
    created_at TEXT, created_by INTEGER
);

CREATE TABLE held_sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT DEFAULT '',
    customer_id INTEGER REFERENCES customers(id),
    payload TEXT NOT NULL,
    cash_session_id INTEGER,
    created_at TEXT, created_by INTEGER, status TEXT DEFAULT 'held'
);

-- --------------------------------------------------------------------------
-- Customer documents: quotes, orders, delivery notes, route notes
-- --------------------------------------------------------------------------
CREATE TABLE quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    valid_until TEXT,
    customer_id INTEGER REFERENCES customers(id),
    customer_snapshot TEXT DEFAULT '',
    subtotal_cents INTEGER NOT NULL DEFAULT 0,
    discount_cents INTEGER NOT NULL DEFAULT 0,
    total_ht_cents INTEGER NOT NULL DEFAULT 0,
    total_vat_cents INTEGER NOT NULL DEFAULT 0,
    total_cents INTEGER NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '',
    terms TEXT DEFAULT '',
    converted_type TEXT DEFAULT '',
    converted_id INTEGER,
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'draft'
);
CREATE TABLE quote_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id INTEGER NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
    ref_type TEXT NOT NULL DEFAULT 'product',
    product_id INTEGER REFERENCES products(id),
    service_id INTEGER REFERENCES services(id),
    code TEXT DEFAULT '', label TEXT NOT NULL, unit TEXT DEFAULT 'u',
    quantity INTEGER NOT NULL DEFAULT 1000,
    unit_price_cents INTEGER NOT NULL DEFAULT 0,
    vat_rate_bp INTEGER NOT NULL DEFAULT 0,
    discount_percent_bp INTEGER NOT NULL DEFAULT 0,
    discount_cents INTEGER NOT NULL DEFAULT 0,
    line_ht_cents INTEGER NOT NULL DEFAULT 0,
    line_vat_cents INTEGER NOT NULL DEFAULT 0,
    line_total_cents INTEGER NOT NULL DEFAULT 0,
    cost_cents INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'client',   -- client | supplier
    party_id INTEGER,
    party_snapshot TEXT DEFAULT '',
    quote_id INTEGER REFERENCES quotes(id),
    expected_date TEXT,
    delivery_address TEXT DEFAULT '',
    subtotal_cents INTEGER NOT NULL DEFAULT 0,
    discount_cents INTEGER NOT NULL DEFAULT 0,
    total_ht_cents INTEGER NOT NULL DEFAULT 0,
    total_vat_cents INTEGER NOT NULL DEFAULT 0,
    total_cents INTEGER NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '',
    terms TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'draft'
);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    ref_type TEXT NOT NULL DEFAULT 'product',
    product_id INTEGER REFERENCES products(id),
    service_id INTEGER REFERENCES services(id),
    code TEXT DEFAULT '', label TEXT NOT NULL, unit TEXT DEFAULT 'u',
    quantity INTEGER NOT NULL DEFAULT 1000,
    delivered_qty INTEGER NOT NULL DEFAULT 0,
    unit_price_cents INTEGER NOT NULL DEFAULT 0,
    vat_rate_bp INTEGER NOT NULL DEFAULT 0,
    discount_percent_bp INTEGER NOT NULL DEFAULT 0,
    discount_cents INTEGER NOT NULL DEFAULT 0,
    line_ht_cents INTEGER NOT NULL DEFAULT 0,
    line_vat_cents INTEGER NOT NULL DEFAULT 0,
    line_total_cents INTEGER NOT NULL DEFAULT 0,
    cost_cents INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE delivery_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    customer_id INTEGER REFERENCES customers(id),
    delivery_address TEXT DEFAULT '',
    source_type TEXT DEFAULT '',
    source_id INTEGER,
    invoice_id INTEGER REFERENCES invoices(id),
    route_note_id INTEGER REFERENCES route_notes(id),
    notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'draft'
);
CREATE TABLE delivery_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id INTEGER NOT NULL REFERENCES delivery_notes(id) ON DELETE CASCADE,
    ref_type TEXT NOT NULL DEFAULT 'product',
    product_id INTEGER REFERENCES products(id),
    code TEXT DEFAULT '', label TEXT NOT NULL, unit TEXT DEFAULT 'u',
    ordered_qty INTEGER NOT NULL DEFAULT 0,
    delivered_qty INTEGER NOT NULL DEFAULT 0,
    remaining_qty INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE route_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    driver_id INTEGER REFERENCES drivers(id),
    vehicle_id INTEGER REFERENCES vehicles(id),
    customer_id INTEGER REFERENCES customers(id),
    delivery_address TEXT DEFAULT '',
    delivery_reference TEXT DEFAULT '',
    departure TEXT DEFAULT '',
    destination TEXT DEFAULT '',
    km INTEGER NOT NULL DEFAULT 0,
    departure_time TEXT DEFAULT '',
    return_time TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'draft'
);
CREATE TABLE route_note_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_note_id INTEGER NOT NULL REFERENCES route_notes(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id),
    label TEXT DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 0,
    delivery_note_id INTEGER REFERENCES delivery_notes(id)
);

-- --------------------------------------------------------------------------
-- Returns
-- --------------------------------------------------------------------------
CREATE TABLE return_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'client',
    party_id INTEGER,
    source_type TEXT DEFAULT '',
    source_id INTEGER,
    source_number TEXT DEFAULT '',
    reason TEXT DEFAULT '',
    condition_code TEXT DEFAULT 'good',
    refund_cents INTEGER NOT NULL DEFAULT 0,
    credit_note_id INTEGER,
    notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'draft'
);
CREATE TABLE return_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id INTEGER NOT NULL REFERENCES return_notes(id) ON DELETE CASCADE,
    ref_type TEXT NOT NULL DEFAULT 'product',
    product_id INTEGER REFERENCES products(id),
    code TEXT DEFAULT '', label TEXT NOT NULL, unit TEXT DEFAULT 'u',
    quantity INTEGER NOT NULL DEFAULT 0,
    unit_price_cents INTEGER NOT NULL DEFAULT 0,
    vat_rate_bp INTEGER NOT NULL DEFAULT 0,
    line_total_cents INTEGER NOT NULL DEFAULT 0,
    reason TEXT DEFAULT '',
    condition_code TEXT DEFAULT 'good',
    restock INTEGER NOT NULL DEFAULT 1
);

-- --------------------------------------------------------------------------
-- Invoicing
-- --------------------------------------------------------------------------
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    due_date TEXT,
    customer_id INTEGER REFERENCES customers(id),
    customer_snapshot TEXT DEFAULT '',
    invoice_type TEXT NOT NULL DEFAULT 'standard',  -- standard|cash|credit|proforma|credit_note
    source_type TEXT DEFAULT '',
    source_id INTEGER,
    subtotal_cents INTEGER NOT NULL DEFAULT 0,
    discount_cents INTEGER NOT NULL DEFAULT 0,
    total_ht_cents INTEGER NOT NULL DEFAULT 0,
    total_vat_cents INTEGER NOT NULL DEFAULT 0,
    total_cents INTEGER NOT NULL DEFAULT 0,
    paid_cents INTEGER NOT NULL DEFAULT 0,
    payment_method TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    terms TEXT DEFAULT '',
    original_invoice_id INTEGER REFERENCES invoices(id),
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'unpaid'
);
CREATE INDEX idx_invoices_customer ON invoices(customer_id);
CREATE INDEX idx_invoices_date ON invoices(date);

CREATE TABLE invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    ref_type TEXT NOT NULL DEFAULT 'product',
    product_id INTEGER REFERENCES products(id),
    service_id INTEGER REFERENCES services(id),
    code TEXT DEFAULT '', label TEXT NOT NULL, unit TEXT DEFAULT 'u',
    quantity INTEGER NOT NULL DEFAULT 1000,
    unit_price_cents INTEGER NOT NULL DEFAULT 0,
    vat_rate_bp INTEGER NOT NULL DEFAULT 0,
    discount_percent_bp INTEGER NOT NULL DEFAULT 0,
    discount_cents INTEGER NOT NULL DEFAULT 0,
    line_ht_cents INTEGER NOT NULL DEFAULT 0,
    line_vat_cents INTEGER NOT NULL DEFAULT 0,
    line_total_cents INTEGER NOT NULL DEFAULT 0,
    cost_cents INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE credit_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    customer_id INTEGER REFERENCES customers(id),
    invoice_id INTEGER REFERENCES invoices(id),
    return_id INTEGER REFERENCES return_notes(id),
    reason TEXT DEFAULT '',
    total_ht_cents INTEGER NOT NULL DEFAULT 0,
    total_vat_cents INTEGER NOT NULL DEFAULT 0,
    total_cents INTEGER NOT NULL DEFAULT 0,
    refunded_cents INTEGER NOT NULL DEFAULT 0,
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'validated'
);
CREATE TABLE credit_note_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credit_note_id INTEGER NOT NULL REFERENCES credit_notes(id) ON DELETE CASCADE,
    ref_type TEXT NOT NULL DEFAULT 'product',
    product_id INTEGER REFERENCES products(id),
    code TEXT DEFAULT '', label TEXT NOT NULL, unit TEXT DEFAULT 'u',
    quantity INTEGER NOT NULL DEFAULT 0,
    unit_price_cents INTEGER NOT NULL DEFAULT 0,
    vat_rate_bp INTEGER NOT NULL DEFAULT 0,
    line_ht_cents INTEGER NOT NULL DEFAULT 0,
    line_vat_cents INTEGER NOT NULL DEFAULT 0,
    line_total_cents INTEGER NOT NULL DEFAULT 0
);

-- --------------------------------------------------------------------------
-- Payments
-- --------------------------------------------------------------------------
CREATE TABLE payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'in',   -- in | out
    party_type TEXT NOT NULL DEFAULT 'customer',
    party_id INTEGER,
    method TEXT NOT NULL DEFAULT 'cash',
    amount_cents INTEGER NOT NULL DEFAULT 0,
    reference TEXT DEFAULT '',
    cash_session_id INTEGER REFERENCES cash_sessions(id),
    notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'validated'
);
CREATE TABLE payment_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    invoice_id INTEGER REFERENCES invoices(id),
    purchase_invoice_id INTEGER,
    amount_cents INTEGER NOT NULL DEFAULT 0
);

-- --------------------------------------------------------------------------
-- Purchases
-- --------------------------------------------------------------------------
CREATE TABLE purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    supplier_id INTEGER REFERENCES suppliers(id),
    supplier_ref TEXT DEFAULT '',
    expected_date TEXT,
    subtotal_cents INTEGER NOT NULL DEFAULT 0,
    discount_cents INTEGER NOT NULL DEFAULT 0,
    total_ht_cents INTEGER NOT NULL DEFAULT 0,
    total_vat_cents INTEGER NOT NULL DEFAULT 0,
    total_cents INTEGER NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'draft'
);
CREATE TABLE purchase_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id),
    code TEXT DEFAULT '', label TEXT NOT NULL, unit TEXT DEFAULT 'u',
    quantity INTEGER NOT NULL DEFAULT 1000,
    received_qty INTEGER NOT NULL DEFAULT 0,
    unit_price_cents INTEGER NOT NULL DEFAULT 0,
    vat_rate_bp INTEGER NOT NULL DEFAULT 0,
    line_ht_cents INTEGER NOT NULL DEFAULT 0,
    line_vat_cents INTEGER NOT NULL DEFAULT 0,
    line_total_cents INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE purchase_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    purchase_id INTEGER REFERENCES purchases(id),
    supplier_id INTEGER REFERENCES suppliers(id),
    notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'validated'
);
CREATE TABLE purchase_receipt_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER NOT NULL REFERENCES purchase_receipts(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id),
    quantity INTEGER NOT NULL DEFAULT 0,
    unit_price_cents INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE purchase_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    due_date TEXT,
    supplier_id INTEGER REFERENCES suppliers(id),
    purchase_id INTEGER REFERENCES purchases(id),
    supplier_invoice_ref TEXT DEFAULT '',
    total_ht_cents INTEGER NOT NULL DEFAULT 0,
    total_vat_cents INTEGER NOT NULL DEFAULT 0,
    total_cents INTEGER NOT NULL DEFAULT 0,
    paid_cents INTEGER NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'unpaid'
);

-- --------------------------------------------------------------------------
-- Stock
-- --------------------------------------------------------------------------
CREATE TABLE stock_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products(id),
    movement_type TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    qty_before INTEGER NOT NULL DEFAULT 0,
    qty_after INTEGER NOT NULL DEFAULT 0,
    unit_cost_cents INTEGER NOT NULL DEFAULT 0,
    location_from TEXT DEFAULT '',
    location_to TEXT DEFAULT '',
    ref_type TEXT DEFAULT '',
    ref_id INTEGER,
    ref_number TEXT DEFAULT '',
    reason TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'validated'
);
CREATE INDEX idx_stock_mov_product ON stock_movements(product_id);
CREATE INDEX idx_stock_mov_date ON stock_movements(date);

CREATE TABLE inventories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    location TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'draft'
);
CREATE TABLE inventory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_id INTEGER NOT NULL REFERENCES inventories(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    expected_qty INTEGER NOT NULL DEFAULT 0,
    counted_qty INTEGER,
    difference INTEGER NOT NULL DEFAULT 0,
    applied INTEGER NOT NULL DEFAULT 0
);

-- --------------------------------------------------------------------------
-- Repairs
-- --------------------------------------------------------------------------
CREATE TABLE repairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    customer_id INTEGER REFERENCES customers(id),
    device_type TEXT DEFAULT '',
    device_brand TEXT DEFAULT '',
    device_model TEXT DEFAULT '',
    serial_number TEXT DEFAULT '',
    accessories TEXT DEFAULT '',
    problem TEXT DEFAULT '',
    diagnosis TEXT DEFAULT '',
    repair_performed TEXT DEFAULT '',
    labor_cents INTEGER NOT NULL DEFAULT 0,
    parts_cents INTEGER NOT NULL DEFAULT 0,
    total_cents INTEGER NOT NULL DEFAULT 0,
    deposit_cents INTEGER NOT NULL DEFAULT 0,
    technician_id INTEGER REFERENCES users(id),
    eta TEXT,
    completed_at TEXT,
    delivered_at TEXT,
    invoice_id INTEGER REFERENCES invoices(id),
    warranty_days INTEGER NOT NULL DEFAULT 0,
    notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'received'
);
CREATE TABLE repair_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repair_id INTEGER NOT NULL REFERENCES repairs(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id),
    code TEXT DEFAULT '', label TEXT NOT NULL, unit TEXT DEFAULT 'u',
    quantity INTEGER NOT NULL DEFAULT 1000,
    unit_price_cents INTEGER NOT NULL DEFAULT 0,
    line_total_cents INTEGER NOT NULL DEFAULT 0
);

-- --------------------------------------------------------------------------
-- Cash register
-- --------------------------------------------------------------------------
CREATE TABLE cash_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    opening_cents INTEGER NOT NULL DEFAULT 0,
    closing_cents INTEGER,
    counted_cents INTEGER,
    difference_cents INTEGER,
    user_id INTEGER REFERENCES users(id),
    notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'open'
);
CREATE TABLE cash_movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER REFERENCES cash_sessions(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    movement_type TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'in',
    amount_cents INTEGER NOT NULL DEFAULT 0,
    method TEXT DEFAULT 'cash',
    ref_type TEXT DEFAULT '',
    ref_id INTEGER,
    ref_number TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT, created_by INTEGER
);
CREATE INDEX idx_cash_mov_session ON cash_movements(session_id);

-- --------------------------------------------------------------------------
-- Expenses
-- --------------------------------------------------------------------------
CREATE TABLE expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    description TEXT DEFAULT '',
    amount_cents INTEGER NOT NULL DEFAULT 0,
    method TEXT DEFAULT 'cash',
    supplier_id INTEGER REFERENCES suppliers(id),
    attachment_path TEXT DEFAULT '',
    cash_session_id INTEGER REFERENCES cash_sessions(id),
    notes TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'validated'
);
CREATE INDEX idx_expenses_date ON expenses(date);

-- --------------------------------------------------------------------------
-- System: documents, licenses, settings, audit
-- --------------------------------------------------------------------------
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type TEXT NOT NULL,
    doc_id INTEGER NOT NULL,
    kind TEXT DEFAULT 'pdf',
    file_path TEXT DEFAULT '',
    created_at TEXT, created_by INTEGER
);

CREATE TABLE licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    license_key TEXT,
    company_name TEXT DEFAULT '',
    user_name TEXT DEFAULT '',
    machine_id TEXT DEFAULT '',
    license_type TEXT DEFAULT 'trial',
    activated_at TEXT,
    expires_at TEXT,
    max_devices INTEGER NOT NULL DEFAULT 1,
    activated_devices INTEGER NOT NULL DEFAULT 1,
    trial_started_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    payload TEXT DEFAULT '',
    signature TEXT DEFAULT '',
    created_at TEXT, updated_at TEXT, created_by INTEGER, status TEXT DEFAULT 'active'
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT DEFAULT '',
    updated_at TEXT, updated_by INTEGER
);

CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    username TEXT DEFAULT '',
    action TEXT NOT NULL,
    entity_type TEXT DEFAULT '',
    entity_id INTEGER,
    details TEXT DEFAULT '',
    ip_address TEXT DEFAULT '',
    hostname TEXT DEFAULT ''
);
CREATE INDEX idx_audit_ts ON audit_logs(timestamp);
CREATE INDEX idx_audit_action ON audit_logs(action);
