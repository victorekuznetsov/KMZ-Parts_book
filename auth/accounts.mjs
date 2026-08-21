/* Учётные записи каталога — файл ведёт build/make_user.mjs.
   Хранятся только хеши PBKDF2-SHA256, их безопасно держать в репозитории.
   AUTH_SECRET в репозиторий не кладётся — он задаётся в Vercel.

   Список пуст намеренно: логины NHL сюда не переносятся, чтобы доступ к
   каталогу КМЗ был отдельным. Пока список пуст, войти нельзя — заведите
   владельца и, при необходимости, временные учётки подрядчиков:

     node build/make_user.mjs set kuznetsov <пароль> --role permanent --name "Кузнецов В.Е."
     node build/make_user.mjs set partner1  <пароль> --role temporary --expires 2026-12-31 --name "Подрядчик"
     node build/make_user.mjs secret        # сгенерировать AUTH_SECRET для Vercel

   После правок — закоммитить этот файл (Vercel передеплоит). */
export default {
  "users": []
};
