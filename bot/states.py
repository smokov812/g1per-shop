from aiogram.fsm.state import State, StatesGroup


class CheckoutStates(StatesGroup):
    customer_name = State()
    contact = State()
    comment = State()
    payment_method = State()
    confirm = State()


class CreateCategoryStates(StatesGroup):
    title = State()
    description = State()


class EditCategoryStates(StatesGroup):
    title = State()


class CreateProductStates(StatesGroup):
    title = State()
    short_description = State()
    full_description = State()
    delivery_content = State()
    price = State()
    sku = State()
    image = State()
    category = State()
    stock_status = State()
    is_active = State()


class EditProductStates(StatesGroup):
    value = State()
    image = State()
    delivery_files = State()


class ManualOrderDeliveryStates(StatesGroup):
    document = State()
