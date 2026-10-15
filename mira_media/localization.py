"""Local Russian, English and Simplified Chinese captions for the native UI.

Russian is the source language. User-entered URLs, file paths, account details
and website contents are never translated. No settings or network are used.
"""

from __future__ import annotations

import re


LANGUAGES = ("ru", "en", "zh_CN")
_language = "ru"
_qt_translator = None
_qt_language = None

# Source | English | Simplified Chinese. Literal \n marks a caption line break.
_ROWS = r"""
Свернуть|Minimize|最小化
Развернуть|Maximize|最大化
Восстановить|Restore|还原
Закрыть|Close|关闭
Загрузка…|Loading…|正在加载…
Папка:|Folder:|文件夹：
Каталог:|Directory:|目录：
Имя файла:|File name:|文件名：
Тип файлов:|Files of type:|文件类型：
Открыть|Open|打开
Подготовка входа|Preparing sign-in|正在准备登录
Обход медиагалереи|Scanning media gallery|正在扫描媒体库
Скачивание|Downloading|正在下载
На паузе|Paused|已暂停
Готово|Done|完成
Остановлено|Stopped|已停止
Ошибка|Error|错误
Прервано|Interrupted|已中断
В очереди|Queued|排队中
В работе|Running|运行中
Создано|Created|已创建
Просмотр|Preview|预览
Завершено с ошибками|Completed with errors|已完成，但有错误
Готова к работе|Ready|准备就绪
Помощь|Help|帮助
Сохраним то, что нравится.|Save what you love.|收藏你喜欢的图片。
Оригиналы в лучшем доступном качестве|Originals in the best available quality|保存可获取的最高画质原图
Ваша коллекция, под вашим контролем|Your collection, under your control|你的收藏，由你掌控
Pixiv · экспериментальный источник|Pixiv · experimental source|Pixiv · 实验性来源
Pixiv · экспериментально. Сначала настройте аккаунт для показа нужного контента: <a href="https://www.pixiv.net/settings/viewing">настройки показа</a>. В окне входа есть такая же кнопка.|Pixiv · experimental. First adjust your account's <a href="https://www.pixiv.net/settings/viewing">viewing settings</a> for the content you need. The sign-in window has the same button.|Pixiv · 实验性支持。请先调整账号的<a href="https://www.pixiv.net/settings/viewing">显示设置</a>，登录窗口中也有相同按钮。
Pixiv — экспериментальный источник|Pixiv — experimental source|Pixiv — 实验性来源
X / Twitter — основной источник|X / Twitter — primary source|X / Twitter — 主要来源
Ссылка на автора: https://x.com/username|Creator URL: https://x.com/username|作者链接：https://x.com/username
Ссылка на автора: https://www.pixiv.net/users/12345|Creator URL: https://www.pixiv.net/users/12345|作者链接：https://www.pixiv.net/users/12345
Вставьте ссылку на профиль автора. X или Pixiv определится автоматически.|Paste a creator's profile URL. X or Pixiv is detected automatically.|粘贴作者主页链接，自动识别 X 或 Pixiv。
Вход не выполнен|Not signed in|尚未登录
Вход сохранён|Sign-in saved|已保存登录状态
Войти в X|Sign in to X|登录 X
Войти в Pixiv|Sign in to Pixiv|登录 Pixiv
Выйти из X|Sign out of X|退出 X
Выйти из Pixiv|Sign out of Pixiv|退出 Pixiv
С|From|起始日期
По|To|截止日期
Папка хранения. Внутри создаются каталоги платформы и ID автора.|Storage folder. Platform and creator ID folders are created inside.|保存文件夹；其中会按平台和作者 ID 创建子文件夹。
Выбрать|Choose|选择
Только новые|New images only|仅下载新图片
Скачать только новые|Download new images only|仅下载新图片
Уже сохранённые изображения проверяются по истории и пропускаются.|Previously saved images are checked against history and skipped.|根据历史记录跳过已保存的图片。
Все даты|All dates|所有日期
Дополнительно|Advanced|更多设置
Найти и скачать|Find and download|查找并下载
За один запуск найти, посчитать и сохранить картинки по мере обнаружения. Предварительный подсчёт не нужен.|Find, count and save images in one run. A separate preview is not required.|一次运行即可查找、计数并保存图片，无需预先统计。
Найти и посчитать|Find and count|查找并统计
Пауза|Pause|暂停
Стоп|Stop|停止
Продолжить|Resume|继续
Обход уточняет число картинок; при скачивании показан прогресс текущего изображения.|The image count grows during scanning; downloading shows the current image's progress.|扫描过程中持续统计图片；下载时显示当前图片的进度。
Вставьте ссылку, выберите папку и нажмите «Найти и скачать».|Paste a URL, choose a folder and click “Find and download”.|粘贴链接，选择文件夹，然后点击“查找并下载”。
Счётчик растёт при обходе. Итог известен после завершения.|The count grows during scanning. The final count is available when scanning finishes.|扫描时数量会增加，完成后显示最终数量。
Счётчик растёт при обходе. Итог доступных картинок известен после завершения.|The count grows during scanning. The final available image count is shown on completion.|扫描时数量会增加，完成后显示可获取图片的最终数量。
Найдено изображений|Images found|已找到图片
Скачано|Downloaded|已下载
Пропущено|Skipped|已跳过
Ошибки|Errors|错误
Найдено|Found|已找到
Найденные и сохранённые изображения|Found and saved images|已找到及已保存的图片
Открыть папку|Open folder|打开文件夹
Открыть пост|Open post|打开帖子
Здесь появятся изображения автора.\nМиниатюры доступны для сохранённых файлов.|The creator's images will appear here.\nThumbnails are available for saved files.|作者的图片将在此显示。\n已保存的文件可显示缩略图。
Двойной щелчок открывает сохранённый файл. Подсчёт не скачивает оригиналы.|Double-click to open a saved file. Counting does not download originals.|双击打开已保存的文件。统计不会下载原图。
Картинки|Images|图片
Задания и контрольные точки|Jobs and checkpoints|任务与检查点
Выберите задание, чтобы восстановить настройки или продолжить после остановки.|Select a job to restore its settings or resume after stopping.|选择任务以恢复设置或继续已停止的任务。
Загрузить настройки|Load settings|载入设置
Продолжить задание|Resume job|继续任务
Обновить|Refresh|刷新
История|History|历史记录
Автор|Creator|作者
Статус|Status|状态
Обновлено|Updated|更新时间
Ошибки и события|Errors and events|错误与事件
Очистить журнал|Clear log|清空日志
Ошибки и важные события появятся здесь. Текст можно выделить и скопировать.|Errors and important events appear here. Text can be selected and copied.|错误及重要事件将在此显示，可选择并复制文本。
Журнал|Log|日志
Дополнительные настройки — Mira|Advanced settings — Mira|更多设置 — Mira
Вход и ограничения запросов|Sign-in and request limits|登录与请求限制
Основной способ — официальный вход в приложении. Дополнительные способы используют только ваши локальные данные.|Use the official sign-in page in the app. Additional methods use only your local data.|首选在应用内通过官方网站登录。其他方式仅使用你的本地数据。
Войти в X в приложении|Sign in to X in the app|在应用内登录 X
Войти в Pixiv в приложении|Sign in to Pixiv in the app|在应用内登录 Pixiv
Из браузера|From browser|从浏览器读取
Из файла cookies.txt|From cookies.txt file|从 cookies.txt 文件读取
Без авторизации|Without sign-in|不登录
Firefox · рекомендуется|Firefox · recommended|Firefox · 推荐
Ваш файл cookies.txt|Your cookies.txt file|你的 cookies.txt 文件
Файл Netscape. Путь и содержимое не сохраняются в настройках.|Netscape file. Its path and contents are not saved in preferences.|Netscape 格式文件；路径及内容不会保存到设置中。
Сохранённый вход Mira|Sign-in saved by Mira|Mira 保存的登录状态
Удалить только вход выбранной платформы, сохранённый Mira на этом компьютере.|Remove only the selected platform's sign-in saved by Mira on this computer.|仅删除 Mira 在此电脑上保存的所选平台登录状态。
Интервал запросов, с|Request interval, s|请求间隔（秒）
Уменьшить интервал на полсекунды|Decrease interval by half a second|将间隔减少半秒
Увеличить интервал на полсекунды|Increase interval by half a second|将间隔增加半秒
Бережная пауза между запросами к сайту. При ограничениях увеличьте интервал.|A gentle pause between site requests. Increase it if the site limits requests.|请求之间保留适当间隔；遇到限制时请增大间隔。
Инфо|Info|信息
Внимание|Warning|注意
Ваш локальный файл cookies|Your local cookies file|你的本地 cookies 文件
Cookies Netscape (*.txt *.cookies);;Все файлы (*)|Netscape cookies (*.txt *.cookies);;All files (*)|Netscape cookies (*.txt *.cookies);;所有文件 (*)
Каталог коллекции|Collection folder|收藏文件夹
Начинаем обход доступной медиагалереи…\nСчётчик обновится по мере обнаружения картинок.|Scanning the accessible media gallery…\nThe count updates as images are found.|正在扫描可访问的媒体库…\n找到图片后会更新数量。
Запуск задания|Starting job|正在启动任务
Подготавливаем локальный обработчик…|Preparing the local worker…|正在准备本地处理程序…
Завершаем текущую операцию и сохраняем контрольную точку…|Finishing the current operation and saving a checkpoint…|正在完成当前操作并保存检查点…
Настройки задания восстановлены. Проверьте сохранённый вход X или выбранный дополнительный способ авторизации.|Job settings restored. Check the saved X sign-in or the selected additional sign-in method.|已恢复任务设置。请检查已保存的 X 登录状态或所选的其他登录方式。
Как пользоваться Mira|How to use Mira|如何使用 Mira
Понятно|Got it|知道了
Завершение задания|Finishing job|结束任务
Текущая операция ещё завершается. Подождать её окончания?\n\nЕсли выбрать «Нет», обработчик будет закрыт принудительно. Уже сохранённые контрольные точки останутся, текущий файл может потребовать повторного скачивания.|The current operation is still finishing. Wait for it?\n\nChoosing “No” closes the worker forcibly. Saved checkpoints remain, but the current file may need to be downloaded again.|当前操作尚未完成。是否等待？\n\n选择“否”将强制关闭处理程序。已保存的检查点会保留，但当前文件可能需要重新下载。
Профили не найдены|No profiles found|未找到浏览器配置文件
Выберите доступный профиль|Choose an available profile|选择可用的配置文件
Не удалось прочитать список профилей. Проверьте доступ и нажмите «Обновить».|Could not read the profile list. Check access and click “Refresh”.|无法读取配置文件列表。请检查访问权限并点击“刷新”。
Firefox: используется обычная сессия профиля. Вход в отдельном контейнере не поддерживается.|Firefox: uses the profile's normal session. Separate-container sign-in is not supported.|Firefox：使用配置文件的普通会话，不支持独立容器中的登录。
Защищённая сессия Chrome, Edge или Brave может быть недоступна. В таком случае используйте Firefox или свой файл cookies.txt.|Protected Chrome, Edge or Brave sessions may be inaccessible. Use Firefox or your own cookies.txt file in that case.|可能无法读取 Chrome、Edge 或 Brave 的受保护会话。此时请使用 Firefox 或自己的 cookies.txt 文件。
Собственный файл Netscape. Путь не запоминается; cookies используются только для выбранной платформы.|Your own Netscape file. Its path is not remembered; cookies are used only for the selected platform.|使用自己的 Netscape 文件。路径不会被记住，cookies 仅用于所选平台。
Только доступ без входа. Доступность картинок ограничена платформой; при отказе задание покажет ошибку.|Access without sign-in only. The platform limits image availability; denied access produces an error.|仅访问无需登录的内容。平台会限制图片可见性；访问被拒绝时任务会显示错误。
Вставьте ссылку на профиль автора.|Paste the creator's profile URL.|请粘贴作者主页链接。
Ссылка и выбранная платформа не совпадают. Выберите нужную платформу или вставьте другую ссылку.|The URL and selected platform do not match. Choose the matching platform or paste another URL.|链接与所选平台不一致。请选择对应的平台或粘贴其他链接。
Начальная дата должна быть не позже конечной.|The start date must not be after the end date.|起始日期不能晚于截止日期。
Выберите каталог хранения.|Choose a storage folder.|请选择保存文件夹。
Выберите свой существующий файл cookies.txt или другой способ авторизации.|Choose your existing cookies.txt file or another sign-in method.|请选择自己的有效 cookies.txt 文件或其他登录方式。
Профиль браузера недоступен. Выберите доступный профиль и нажмите «Обновить». Способ авторизации сохранён.|The browser profile is unavailable. Choose an available profile and click “Refresh”. The sign-in method is retained.|浏览器配置文件不可用。请选择可用的配置文件并点击“刷新”。登录方式会保留。
Не удалось удалить сохранённый вход Mira. Проверьте доступ к локальным данным приложения.|Could not remove the saved Mira sign-in. Check access to the app's local data.|无法删除 Mira 保存的登录状态。请检查应用本地数据的访问权限。
Не удалось открыть каталог хранения. Выберите доступную папку.|Could not open the storage folder. Choose an accessible folder.|无法打开保存文件夹。请选择可访问的文件夹。
Не удалось сохранить запрос задания. Проверьте права на каталог.|Could not save the job request. Check folder permissions.|无法保存任务请求。请检查文件夹权限。
Запущен подсчёт доступных картинок.|Counting available images.|已开始统计可获取的图片。
Задание запущено. Контрольные точки сохраняются автоматически.|Job started. Checkpoints are saved automatically.|任务已启动，检查点将自动保存。
Слишком длинное служебное сообщение пропущено.|An overly long service message was skipped.|已跳过过长的服务消息。
Оригинал ещё не сохранён. Во время подсчёта картинки не скачиваются.|The original is not saved yet. Counting does not download images.|原图尚未保存。统计时不会下载图片。
Папка будет создана при запуске задания.|The folder will be created when a job starts.|启动任务时将创建文件夹。
Продолжаем задание…|Resuming job…|正在继续任务…
Пауза будет применена после текущей операции…|Pausing after the current operation…|将在当前操作完成后暂停…
Не удалось запустить|Could not start|无法启动
Не удалось запустить обработчик. Проверьте комплектность приложения и доступ к каталогу.|Could not start the worker. Check that the app package is complete and the folder is accessible.|无法启动处理程序。请检查应用文件是否完整，以及文件夹是否可访问。
Обработчик завершил работу. Состояние доступно в истории заданий.|The worker has exited. Its state is available in job history.|处理程序已退出。任务状态可在历史记录中查看。
В выбранном диапазоне пока нет карточек.\nПроверьте журнал, доступ к профилю и выбранные даты.|No image cards in this range yet.\nCheck the log, profile access and selected dates.|所选范围内暂时没有图片。\n请检查日志、主页访问权限和所选日期。
 · подсчёт| · count| · 统计
\nСохранено|\nSaved|\n已保存
Сохранено|Saved|已保存
Картинка найдена|Image found|已找到图片
\nБез локального превью|\nNo local preview|\n无本地预览
Без локального превью|No local preview|无本地预览
Задание прервано|Job interrupted|任务已中断
Задание завершено|Job completed|任务已完成
Не удалось прочитать историю из выбранной коллекции.|Could not read history from the selected collection.|无法读取所选收藏文件夹的历史记录。
Задание|Job|任务
Сохраняем состояние|Saving state|正在保存状态
Обработчик вернул нечитаемое сообщение. Задание продолжает работу.|The worker returned an unreadable message. The job continues.|处理程序返回了无法读取的消息。任务将继续运行。
Обход завершён. Показано число доступных картинок в выбранных датах.|Scanning finished. The available image count for the selected dates is shown.|扫描已完成。现已显示所选日期内可获取图片的数量。
Показаны первые 800 карточек. Полный результат и контрольные точки сохранены в коллекции.|Showing the first 800 image cards. Full results and checkpoints are saved in the collection.|仅显示前 800 张图片卡片。完整结果和检查点已保存在收藏文件夹中。
Изображение автора|Creator image|作者图片
Сохранена контрольная точка. Это число картинок, найденных до остановки.|Checkpoint saved. This is the number of images found before stopping.|检查点已保存。此数量为停止前找到的图片数。
Обход завершён, часть файлов не скачана. Продолжите задание из истории, чтобы повторить попытку.|Scanning finished, but some files were not downloaded. Resume the job from history to retry.|扫描已完成，但部分文件未下载。请从历史记录继续任务以重试。
Задание завершилось с ошибкой. Найденное число может быть неполным.|The job ended with an error. The image count may be incomplete.|任务因错误结束，找到的图片数量可能不完整。
Пароль и коды вводятся только в официальную страницу сайта ниже.|Enter passwords and codes only on the official site below.|仅在下方官方网站页面中输入密码和验证码。
Выполните вход и все проверки сайта. Затем нажмите «Сохранить вход».|Sign in and complete the site's checks. Then click “Save sign-in”.|请登录并完成网站要求的验证，然后点击“保存登录状态”。
Повторить загрузку|Reload page|重新加载页面
Проверить вход|Check sign-in|检查登录状态
Открыть главную Pixiv и проверить подтверждённый вход; гостевая сессия не подходит.|Open the Pixiv homepage and verify account sign-in; a guest session is insufficient.|打开 Pixiv 首页并验证账号登录；访客会话无效。
Проверить вход в Pixiv; гостевая сессия не подходит.|Verify Pixiv account sign-in; a guest session is insufficient.|验证 Pixiv 账号登录；访客会话无效。
Настройки показа|Viewing settings|显示设置
Сначала настройте аккаунт Pixiv для показа нужного контента. Изменения выполняете вы на сайте Pixiv.|First adjust your Pixiv account's viewing settings. You make these changes yourself on Pixiv.|请先在 Pixiv 网站自行调整账号的显示设置。
Отмена|Cancel|取消
Сохранить вход|Save sign-in|保存登录状态
Проверяем вход на главной странице Pixiv. Пароли и содержимое форм не читаются.|Checking sign-in on the Pixiv homepage. Passwords and form contents are not read.|正在 Pixiv 首页检查登录状态，不会读取密码或表单内容。
Проверяем вход в Pixiv. Пароли и содержимое форм не читаются.|Checking Pixiv sign-in. Passwords and form contents are not read.|正在检查 Pixiv 登录状态，不会读取密码或表单内容。
Закрываем окно входа…|Closing sign-in window…|正在关闭登录窗口…
Неизвестная платформа входа.|Unknown sign-in platform.|未知的登录平台。
Вход в аккаунт Pixiv пока не подтверждён. Завершите вход и нажмите «Проверить вход». Гостевой сессии недостаточно; при изменении сайта проверка может быть недоступна.|Pixiv account sign-in is not confirmed yet. Finish signing in and click “Check sign-in”. A guest session is insufficient; site changes may prevent verification.|尚未确认 Pixiv 账号登录。请完成登录并点击“检查登录状态”。访客会话无效；网站变更可能导致无法验证。
Не удалось безопасно сохранить вход средствами Windows. Проверьте доступ к локальным данным приложения и попробуйте снова.|Could not securely save sign-in using Windows protection. Check access to the app's local data and try again.|无法使用 Windows 保护机制安全保存登录状态。请检查应用本地数据的访问权限后重试。
Предыдущий месяц|Previous month|上个月
Следующий месяц|Next month|下个月
На год назад|Previous year|上一年
Предыдущий год|Previous year|上一年
Сегодня|Today|今天
Сегодняшняя дата по UTC|Today's date in UTC|今天的 UTC 日期
На год вперёд|Next year|下一年
Следующий год|Next year|下一年
Период загрузки|Download period|下载日期范围
Выберите даты публикаций, которые нужно найти и скачать.|Choose publication dates for the images to find and download.|选择要查找并下载的图片的发布日期范围。
Не ограничивать дату публикации.|Do not restrict the publication date.|不限制发布日期。
Выбрать период|Choose a period|选择日期范围
Можно указать обе границы или только одну.|Set both bounds or just one.|可设置两个日期边界，也可仅设置一个。
Указать начало периода|Set start date|设置起始日期
Указать конец периода|Set end date|设置截止日期
Обе границы включаются целиком. Даты публикаций считаются по UTC.|Both dates are inclusive. Publication dates use UTC.|起止日期均包含在内，发布日期按 UTC 计算。
Ошибка периода|Date range error|日期范围错误
Применить|Apply|应用
Дата периода должна иметь формат ГГГГ-ММ-ДД.|Dates must use YYYY-MM-DD format.|日期格式必须为 YYYY-MM-DD。
Выберите действующую дату от 1 до 9999 года.|Choose a valid date between years 1 and 9999.|请选择公元 1 至 9999 年之间的有效日期。
Начало периода, UTC|Start date, UTC|起始日期（UTC）
Конец периода, UTC|End date, UTC|截止日期（UTC）
Открыть календарь. Дата публикации по UTC, включительно.|Open calendar. Publication date in UTC, inclusive.|打开日历，选择包含在范围内的 UTC 发布日期。
Выберите хотя бы одну границу периода или «Все даты».|Choose at least one date bound, or select “All dates”.|请至少设置一个日期边界，或选择“所有日期”。
Начало периода должно быть раньше окончания или совпадать с ним.|The start date must be before or equal to the end date.|起始日期必须早于或等于截止日期。
Язык|Language|语言
Язык интерфейса|Interface language|界面语言
Границы включительно, даты публикации в UTC.|Inclusive bounds; publication dates in UTC.|包含起止日期，发布日期按 UTC 计算。
Тема|Theme|主题
Светлая|Light|浅色
Тёмная|Dark|深色
Светлая тема|Light theme|浅色主题
Тёмная тема|Dark theme|深色主题
Переключить тему|Switch theme|切换主题
Выбрать язык|Choose language|选择语言
Обход доступной медиагалереи · считаем изображения|Scanning accessible media · counting images|正在扫描可访问的媒体库并统计图片
Продолжаем обход · общее число ещё уточняется|Continuing scan · the total is still being determined|继续扫描 · 总数仍在统计中
Остановлено. Состояние сохранено.|Stopped. State saved.|已停止，状态已保存。
Остановлено · продолжение доступно в истории|Stopped · resume from history|已停止 · 可从历史记录继续
На паузе · состояние сохранено|Paused · state saved|已暂停 · 状态已保存
Продолжение задания|Resuming job|继续任务
Читаем сессию из выбранного браузера локально|Reading the selected browser's session locally|正在本地读取所选浏览器会话
Предпросмотр: считаем доступные изображения без загрузки оригиналов.|Preview: counting available images without downloading originals.|预览：统计可获取的图片，不下载原图。
Задание запущено. Очередь и результаты сохраняются после каждого изображения.|Job started. The queue and results are saved after each image.|任务已启动，每处理一张图片后保存队列和结果。
Количество относится только к изображениям, которые платформа вернула для текущего доступа и периода. Полнота всей истории не гарантируется.|The count includes only images returned for the current access and date range. A complete history is not guaranteed.|数量仅包含当前权限及日期范围内平台返回的图片，无法保证历史记录完整。
Не удалось записать данные. Проверьте свободное место и доступ к выбранной папке.|Could not write data. Check free space and access to the selected folder.|无法写入数据。请检查磁盘空间及所选文件夹的访问权限。
Слишком много перенаправлений платформы.|Too many platform redirects.|平台重定向次数过多。
Pixiv подтвердил вход для текущего задания. Доступность работ определяется аккаунтом и настройками сайта.|Pixiv sign-in confirmed for this job. Artwork availability depends on the account and site settings.|已确认此任务的 Pixiv 登录状态。作品可见性取决于账号及网站设置。
Pixiv: загружаются явно возвращённые оригиналы иллюстраций и манги; ugoira пропускается.|Pixiv: downloading only returned illustration and manga originals; ugoira is skipped.|Pixiv：仅下载网站明确返回的插画及漫画原图，跳过 ugoira。
Pixiv не подтвердил вход. Войдите в Pixiv заново и повторите задание.|Pixiv did not confirm sign-in. Sign in to Pixiv again and retry the job.|Pixiv 未确认登录状态，请重新登录后重试任务。
Источник предложил неподдерживаемый адрес. Загрузка остановлена.|The source returned an unsupported address. Download stopped.|来源返回了不支持的地址，下载已停止。
Источник запросил неподдерживаемое действие.|The source requested an unsupported action.|来源请求了不支持的操作。
Источник повторяет одну страницу без продвижения. Задание остановлено.|The source is repeating a page without progressing. Job stopped.|来源重复返回同一页面，任务已停止。
Выберите локальный Netscape cookies.txt размером не более 10 МБ.|Choose a local Netscape cookies.txt file no larger than 10 MB.|请选择不超过 10 MB 的本地 Netscape cookies.txt 文件。
Не удалось прочитать cookies. Нужен локальный файл Netscape cookies.txt.|Could not read cookies. A local Netscape cookies.txt file is required.|无法读取 cookies，需要本地 Netscape cookies.txt 文件。
Источник сообщил о пропуске или изменении данных; доступность может быть ограничена.|The source reported skipped or changed data; availability may be limited.|来源报告数据已跳过或发生变化，可见性可能受限。
Начальная дата должна предшествовать конечной.|The start date must precede the end date.|起始日期应早于截止日期。
Задание уже закрыто.|The job is already closed.|任务已关闭。
X не предоставил числовой ID автора. Загрузка остановлена для корректного выбора каталога.|X did not provide a numeric creator ID. Download stopped to avoid choosing an incorrect folder.|X 未提供作者数字 ID。为避免选择错误的文件夹，下载已停止。
Pixiv без входа: часть публикаций может не отображаться. Для доступной вашему аккаунту галереи выполните вход.|Pixiv without sign-in: some artworks may be hidden. Sign in to access your account's available gallery.|未登录 Pixiv 时可能看不到部分作品。请登录以获取账号可访问的作品。
Pixiv изменил формат галереи.|Pixiv changed its gallery format.|Pixiv 已更改作品列表格式。
Платформа перенаправила запрос за пределы разрешённого источника.|The platform redirected the request outside the allowed source.|平台将请求重定向到了允许来源之外。
Дата должна иметь формат ГГГГ-ММ-ДД.|The date must use YYYY-MM-DD format.|日期格式必须为 YYYY-MM-DD。
Источник требует повторного входа. Нажмите «Войти в X» либо войдите в выбранном браузере заново.|The source requires a new sign-in. Click “Sign in to X” or sign in again in the selected browser.|来源要求重新登录。请点击“登录 X”，或在所选浏览器中重新登录。
Версия backend не поддерживает медиагалерею X.|This backend version does not support the X media gallery.|当前后端版本不支持 X 媒体库。
Pixiv не предоставил запрошенные данные. Проверьте доступность в браузере.|Pixiv did not provide the requested data. Check access in your browser.|Pixiv 未提供请求的数据，请在浏览器中检查是否可访问。
Pixiv изменил формат ответа; обход остановлен.|Pixiv changed its response format; scanning stopped.|Pixiv 已更改响应格式，扫描已停止。
Pixiv не предоставил галерею. Проверьте вход и доступность профиля на сайте.|Pixiv did not provide a gallery. Check sign-in and profile access on the site.|Pixiv 未提供作品列表，请在网站上检查登录状态及主页访问权限。
Pixiv вернул неожиданные данные; требуется проверка поддержки платформы.|Pixiv returned unexpected data; platform support needs checking.|Pixiv 返回了异常数据，需要检查平台支持情况。
Pixiv изменил формат списка публикаций.|Pixiv changed its artwork list format.|Pixiv 已更改作品列表格式。
Pixiv: недоступная публикация пропущена.|Pixiv: unavailable artwork skipped.|Pixiv：已跳过不可访问的作品。
Pixiv изменил формат публикации; обход остановлен.|Pixiv changed its artwork format; scanning stopped.|Pixiv 已更改作品数据格式，扫描已停止。
Pixiv: изображения недоступной публикации пропущены.|Pixiv: unavailable artwork images skipped.|Pixiv：已跳过不可访问作品的图片。
Достигнут предел запросов одного задания. Продолжите новым запуском.|The request limit for this job was reached. Continue with a new run.|已达到此任务的请求上限，请重新运行以继续。
Сессия прочитана из выбранного профиля браузера локально. Cookies используются только в памяти.|The selected browser profile's session was read locally. Cookies are used only in memory.|已在本地读取所选浏览器配置文件的会话，cookies 仅在内存中使用。
Не удалось прочитать медиагалерею X. Проверьте доступ в браузере, cookies и обновление backend.|Could not read the X media gallery. Check browser access, cookies and backend updates.|无法读取 X 媒体库。请检查浏览器访问权限、cookies 及后端更新。
Pixiv изменил формат страниц публикации; обход остановлен.|Pixiv changed its artwork page format; scanning stopped.|Pixiv 已更改作品页面格式，扫描已停止。
Pixiv: оригинал отсутствует или имеет неподдерживаемый адрес; пропуск.|Pixiv: original missing or unsupported address; skipped.|Pixiv：缺少原图或地址不受支持，已跳过。
Ошибка безопасного соединения с платформой.|Secure connection to the platform failed.|与平台的安全连接失败。
Источник изменил формат галереи; требуется обновление приложения.|The source changed its gallery format; an app update is required.|来源已更改媒体库格式，需要更新应用。
X требует действующую авторизацию или не разрешает доступ. Нажмите «Войти в X» либо проверьте выбранный способ авторизации.|X requires valid sign-in or does not allow access. Click “Sign in to X” or check the selected sign-in method.|X 要求有效登录或不允许访问。请点击“登录 X”，或检查所选登录方式。
Не удалось связаться с платформой после ограниченного числа попыток.|Could not reach the platform after a limited number of retries.|在有限次数的重试后仍无法连接平台。
Платформа отклонила доступ (HTTP 401/403). Проверьте права доступа и выполните вход заново.|The platform denied access (HTTP 401/403). Check permissions and sign in again.|平台拒绝访问（HTTP 401/403）。请检查权限并重新登录。
Платформа ограничила запросы (HTTP 429). Задание остановлено; повторите позже.|The platform limited requests (HTTP 429). Job stopped; retry later.|平台限制了请求（HTTP 429），任务已停止，请稍后重试。
Не удалось загрузить изображение.|Could not download the image.|无法下载图片。
Платформа не вернула числовой ID автора. Загрузка остановлена.|The platform did not return a numeric creator ID. Download stopped.|平台未返回作者数字 ID，下载已停止。
Платформа вернула некорректный идентификатор изображения.|The platform returned an invalid image identifier.|平台返回了无效的图片标识符。
Неподдерживаемый формат изображения.|Unsupported image format.|不支持的图片格式。
Неизвестная платформа.|Unknown platform.|未知平台。
Путь выходит за пределы выбранной папки.|The path is outside the selected folder.|路径超出了所选文件夹。
Достигнут лимит запросов (HTTP 429). Состояние сохранено; продолжите позже.|Request limit reached (HTTP 429). State saved; resume later.|已达到请求限制（HTTP 429），状态已保存，请稍后继续。
Вместо изображения сервер вернул другой тип данных.|The server returned another data type instead of an image.|服务器返回了其他类型的数据，而非图片。
Изображение превышает предел 512 МБ.|The image exceeds the 512 MB limit.|图片超过 512 MB 限制。
Адрес изображения не принадлежит разрешённому медиасерверу.|The image address is not on an allowed media server.|图片地址不属于允许的媒体服务器。
Полученное изображение повреждено или имеет неподдерживаемый формат.|The received image is damaged or uses an unsupported format.|接收到的图片已损坏或格式不受支持。
Сеть недоступна или ответ прервался. Повторите задание для продолжения.|The network is unavailable or the response was interrupted. Retry the job to resume.|网络不可用或响应中断，请重试任务以继续。
Слишком много перенаправлений медиасервера.|Too many media-server redirects.|媒体服务器重定向次数过多。
Неизвестная платформа для сохранённой сессии.|Unknown platform for the saved session.|保存会话的平台未知。
Неизвестный режим задания.|Unknown job mode.|未知任务模式。
Выберите абсолютный путь к папке хранения.|Choose an absolute storage-folder path.|请选择保存文件夹的绝对路径。
Начало периода должно быть раньше его окончания.|The start date must be before the end date.|起始日期必须早于截止日期。
Выберите вход в приложении, браузер, файл или режим без авторизации.|Choose in-app sign-in, browser, file or unsigned access.|请选择应用内登录、浏览器、文件或不登录模式。
Выбранный файл cookies не найден. Выберите его заново.|The selected cookies file was not found. Choose it again.|找不到所选 cookies 文件，请重新选择。
Выберите поддерживаемый браузер.|Choose a supported browser.|请选择受支持的浏览器。
Выберите профиль браузера, в котором выполнен вход в X.|Choose the browser profile signed in to X.|请选择已登录 X 的浏览器配置文件。
Интервал запросов должен быть конечным числом.|The request interval must be a finite number.|请求间隔必须为有限数值。
Поддерживаются только профили x.com, twitter.com и опционально pixiv.net.|Only x.com, twitter.com and optional pixiv.net profiles are supported.|仅支持 x.com、twitter.com 及可选的 pixiv.net 作者主页。
Некорректная ссылка.|Invalid URL.|链接无效。
Используйте HTTPS-ссылку на профиль X или Pixiv.|Use an HTTPS profile URL for X or Pixiv.|请使用 X 或 Pixiv 的 HTTPS 主页链接。
Нужна ссылка на профиль X: https://x.com/имя или /имя/media.|Use an X profile URL: https://x.com/name or /name/media.|请使用 X 主页链接：https://x.com/name 或 /name/media。
Нужна ссылка Pixiv вида https://www.pixiv.net/users/12345.|Use a Pixiv URL like https://www.pixiv.net/users/12345.|请使用类似 https://www.pixiv.net/users/12345 的 Pixiv 链接。
Pixiv отключён. Включите экспериментальный адаптер в настройках.|Pixiv is disabled. Enable the experimental adapter in settings.|Pixiv 已禁用，请在设置中启用实验性适配器。
Не удалось прочитать cookies выбранного профиля. Браузер мог заблокировать базу или изменить её формат. Попробуйте Firefox либо собственный файл cookies; приложение не снимает блокировки браузера.|Could not read the selected profile's cookies. The browser may have locked the database or changed its format. Try Firefox or your own cookies file; the app does not bypass browser locks.|无法读取所选配置文件的 cookies。浏览器可能锁定了数据库或更改了格式。请尝试 Firefox 或自己的 cookies 文件；应用不会绕过浏览器锁定。
Браузер защищает выбранную сессию шифрованием, привязанным к приложению (App-Bound/v20). Mira не обходит эту защиту. Выберите профиль Firefox либо собственный файл cookies.|The browser protects this session with app-bound encryption (App-Bound/v20). Mira does not bypass it. Choose a Firefox profile or your own cookies file.|浏览器使用应用绑定加密（App-Bound/v20）保护此会话。Mira 不会绕过此保护，请选择 Firefox 配置文件或自己的 cookies 文件。
Не удалось расшифровать cookies обычным механизмом Windows для текущего пользователя. Выберите профиль Firefox либо собственный файл cookies.|Could not decrypt cookies using normal Windows protection for the current user. Choose a Firefox profile or your own cookies file.|无法使用当前用户的常规 Windows 保护机制解密 cookies。请选择 Firefox 配置文件或自己的 cookies 文件。
Этот браузер не поддерживается. Выберите Firefox, Chrome, Edge или Brave.|This browser is unsupported. Choose Firefox, Chrome, Edge or Brave.|不支持此浏览器，请选择 Firefox、Chrome、Edge 或 Brave。
В профиле слишком много подходящих записей cookies. Выберите другой собственный профиль.|The profile contains too many matching cookie records. Choose another profile you own.|配置文件中匹配的 cookies 记录过多，请选择自己的其他配置文件。
Выбранный профиль браузера не найден. Обновите список и выберите собственный профиль.|The selected browser profile was not found. Refresh the list and choose a profile you own.|找不到所选浏览器配置文件，请刷新列表并选择自己的配置文件。
Неизвестная платформа для импорта cookies.|Unknown platform for cookie import.|导入 cookies 的平台未知。
В выбранном профиле не найдена база cookies. Войдите на сайт в этом профиле браузера.|No cookies database found in the selected profile. Sign in to the site in that browser profile.|所选配置文件中找不到 cookies 数据库，请在该浏览器配置文件中登录网站。
Некорректные данные сессии браузера. Войдите на сайт заново.|Invalid browser session data. Sign in to the site again.|浏览器会话数据无效，请重新登录网站。
В выбранном профиле найдены разные сессии сайта. Выберите другой профиль или войдите на сайт заново.|Different site sessions were found in the selected profile. Choose another profile or sign in again.|所选配置文件中存在不同的网站会话，请选择其他配置文件或重新登录。
В выбранном профиле не найдена действующая сессия сайта. Войдите на сайт в этом профиле браузера.|No active site session found in the selected profile. Sign in to the site in that browser profile.|所选配置文件中未找到有效的网站会话，请在该浏览器配置文件中登录网站。
В этой папке уже работает другое задание. Дождитесь его завершения.|Another job is already using this folder. Wait for it to finish.|已有其他任务正在使用此文件夹，请等待其完成。
Некорректный размер служебного запроса.|Invalid job request size.|任务请求大小无效。
Некорректный запрос задания.|Invalid job request.|任务请求无效。
Не удалось запустить задание. Проверьте настройки и комплектность приложения.|Could not start the job. Check settings and that the app package is complete.|无法启动任务，请检查设置及应用文件是否完整。
Оригинальный размер не найден (HTTP 404). Проверяем следующий доступный размер.|Original size not found (HTTP 404). Trying the next available size.|未找到原始尺寸（HTTP 404），正在尝试下一个可用尺寸。
"""

_TEMPLATE_ROWS = r"""
Войти в {platform}|Sign in to {platform}|登录 {platform}
Подключаем сохранённый вход {platform}|Restoring saved {platform} sign-in|正在恢复保存的 {platform} 登录状态
Подключён сохранённый вход {platform}. Сессия расшифрована только в памяти текущего задания.|Saved {platform} sign-in restored. The session was decrypted only in this job's memory.|已恢复保存的 {platform} 登录状态，会话仅在当前任务的内存中解密。
Войти в {platform} в приложении|Sign in to {platform} in the app|在应用内登录 {platform}
Выйти из {platform}|Sign out of {platform}|退出 {platform}
Вход на официальном сайте {platform}|Sign in on the official {platform} site|在 {platform} 官方网站登录
Адрес официальной страницы {platform}; изменить нельзя|Official {platform} page address; cannot be edited|{platform} 官方页面地址，无法修改
Открыть официальную страницу входа {platform} прямо в приложении.|Open the official {platform} sign-in page in the app.|在应用内打开 {platform} 官方登录页面。
Вход в {platform} сохранён. Можно считать и скачивать картинки доступных авторов.|{platform} sign-in saved. You can count and download accessible creator images.|已保存 {platform} 登录状态，可以统计和下载可访问的作者图片。
Не удалось открыть встроенный вход {platform}. Проверьте комплектность приложения или используйте дополнительный способ авторизации.|Could not open embedded {platform} sign-in. Check the app package or use an additional sign-in method.|无法打开应用内 {platform} 登录。请检查应用文件是否完整，或使用其他登录方式。
Нажмите «Войти в {platform}», войдите на официальной странице и сохраните вход. Сессии платформ хранятся отдельно и защищены Windows. Доступность контента зависит от аккаунта.|Click “Sign in to {platform}”, sign in on the official page and save it. Platform sessions are separate and protected by Windows. Content availability depends on your account.|点击“登录 {platform}”，在官方页面登录并保存登录状态。各平台会话独立保存，并受 Windows 保护；内容可见性取决于账号。
Нажмите «Войти в {platform}», завершите вход на официальной странице и нажмите «Сохранить вход».|Click “Sign in to {platform}”, finish signing in on the official page, then click “Save sign-in”.|点击“登录 {platform}”，在官方页面完成登录后点击“保存登录状态”。
Вход {platform} в Mira удалён с этого компьютера. Это не завершает другие сеансы {platform}; при необходимости отзовите их в настройках {platform}.|The {platform} sign-in saved by Mira was removed from this computer. Other {platform} sessions remain active; revoke them in {platform} settings if needed.|已从此电脑删除 Mira 保存的 {platform} 登录状态。其他 {platform} 会话仍保持登录；如需撤销，请前往 {platform} 设置。
Профиль недоступен. Выберите профиль или запустите браузер, войдите в {platform} и нажмите «Обновить».|Profile unavailable. Choose a profile or open the browser, sign in to {platform} and click “Refresh”.|配置文件不可用。请选择配置文件，或打开浏览器登录 {platform} 后点击“刷新”。
Войдите в {platform} в выбранном профиле. Cookies читаются локально только при запуске задания.|Sign in to {platform} in the selected profile. Cookies are read locally only when a job starts.|请在所选配置文件中登录 {platform}。只有启动任务时才会在本地读取 cookies。
Войдите обычным способом в {platform}. Пароль и коды получает сам сайт. Внешние страницы Google, Apple и других способов входа в этом окне недоступны. Ключи доступа Windows Hello здесь не поддерживаются — используйте вход по паролю.|Sign in to {platform} normally. The site receives your password and codes. External Google, Apple and other sign-in pages are unavailable here. Windows Hello passkeys are not supported in this window; use password sign-in.|请正常登录 {platform}。密码和验证码由网站接收。此窗口不支持 Google、Apple 等外部登录页面，也不支持 Windows Hello 通行密钥；请使用密码登录。
Внешняя страница заблокирована. Продолжайте обычный вход на сайте {platform}; внешние способы входа не поддерживаются.|External page blocked. Continue normal sign-in on {platform}; external sign-in methods are not supported.|已拦截外部页面。请继续在 {platform} 网站正常登录；不支持外部登录方式。
Страница {platform} не загрузилась. Проверьте соединение и повторите. Если сайт ограничивает встроенный вход, используйте другой способ в главном окне.|The {platform} page did not load. Check your connection and retry. If the site restricts embedded sign-in, use another method in the main window.|未能加载 {platform} 页面。请检查网络后重试。如果网站限制应用内登录，请在主窗口选择其他方式。
Вход в {platform} подтверждён. Завершите проверки сайта, затем нажмите «Сохранить вход».|{platform} sign-in confirmed. Complete the site's checks, then click “Save sign-in”.|已确认 {platform} 登录。请完成网站验证，然后点击“保存登录状态”。
Внутри выбранной папки: {platform}\ID автора\|Inside the chosen folder: {platform}\Creator ID\|所选文件夹内：{platform}\作者 ID\
С {date}|From {date}|自 {date}
По {date}|To {date}|至 {date}
{range}. Границы включительно, даты публикации в UTC.|{range}. Inclusive bounds; publication dates in UTC.|{range}。包含起止日期，发布日期按 UTC 计算。
Обработчик завершился с кодом {code}. Контрольная точка хранится в коллекции.|The worker exited with code {code}. Its checkpoint is stored in the collection.|处理程序以代码 {code} 退出，检查点已保存在收藏文件夹中。
Пост {post}|Post {post}|帖子 {post}
Пост {post_id}|Post {post_id}|帖子 {post_id}
Пост {post}, изображение {index}: {message}|Post {post}, image {index}: {message}|帖子 {post}，图片 {index}：{message}
Загрузка · пост {post}, изображение {index}|Downloading · post {post}, image {index}|正在下载 · 帖子 {post}，图片 {index}
Доступный обход завершён · найдено изображений: {count}|Accessible scan completed · images found: {count}|可访问内容扫描完成 · 找到图片：{count}
Обход завершён с ошибками: найдено {count}, ошибок {errors}. Повторите для загрузки пропущенных.|Scan completed with errors: {count} found, {errors} errors. Retry to download missing images.|扫描已完成但出现错误：找到 {count} 张，错误 {errors} 个。请重试以下载缺失图片。
Не удалось определить дату у {count} изображений: исключены фильтром периода.|Could not determine the date of {count} images; excluded by the date filter.|无法确定 {count} 张图片的日期，已按日期筛选规则排除。
Сетевой сбой: повтор {attempt} из 2 после задержки.|Network failure: retry {attempt} of 2 after a delay.|网络错误：延迟后进行第 {attempt}/2 次重试。
Неожиданная ошибка ({error_type}). Состояние сохранено; повторите задание.|Unexpected error ({error_type}). State saved; retry the job.|发生意外错误（{error_type}），状态已保存，请重试任务。
Медиасервер ограничил доступ (HTTP {status}). Проверьте свою авторизацию и повторите позже.|The media server denied access (HTTP {status}). Check sign-in and retry later.|媒体服务器限制访问（HTTP {status}），请检查登录状态后稍后重试。
Изображение недоступно (HTTP {status}).|Image unavailable (HTTP {status}).|图片不可获取（HTTP {status}）。
Пост {post}: одинаковое содержимое уже есть, дополнительный файл не создан.|Post {post}: duplicate content already exists; no additional file was created.|帖子 {post}：相同内容已存在，未创建额外文件。
Сессия {platform} не сохранена. Войдите в {platform} через окно приложения.|No {platform} session saved. Sign in to {platform} in the app.|未保存 {platform} 会话，请在应用内登录 {platform}。
Сохранённая сессия {platform} недоступна или истекла. Войдите в {platform} заново.|The saved {platform} session is unavailable or expired. Sign in to {platform} again.|保存的 {platform} 会话不可用或已过期，请重新登录 {platform}。
Не получена полная действующая сессия {platform}. Завершите вход в окне приложения.|A complete valid {platform} session was not obtained. Finish signing in in the app.|未获取完整有效的 {platform} 会话，请在应用内完成登录。
Не удалось безопасно сохранить сессию {platform} для текущего пользователя Windows. Повторите вход.|Could not securely save the {platform} session for the current Windows user. Sign in again.|无法为当前 Windows 用户安全保存 {platform} 会话，请重新登录。
Не удалось удалить сохранённую сессию {platform}. Закройте другие окна Mira и повторите.|Could not remove the saved {platform} session. Close other Mira windows and retry.|无法删除保存的 {platform} 会话，请关闭其他 Mira 窗口后重试。
{message} Используется обычный вход Firefox вне контейнеров и приватных окон.|{message} Use Firefox's normal sign-in outside containers and private windows.|{message} 请使用 Firefox 容器及隐私窗口之外的普通登录。
Pixiv: публикация {post} содержит {expected} страниц, сайт вернул {actual}. Сохранены только доступные оригиналы.|Pixiv: artwork {post} has {expected} pages; the site returned {actual}. Only available originals are saved.|Pixiv：作品 {post} 共 {expected} 页，网站返回 {actual} 页。仅保存可获取的原图。
Pixiv: недоступных публикаций — {posts}; недоступных страниц — {pages}; анимаций ugoira — {ugoira}. Они не включены в число найденных изображений.|Pixiv: unavailable artworks — {posts}; unavailable pages — {pages}; ugoira animations — {ugoira}. They are not included in the image count.|Pixiv：不可访问的作品 {posts} 个；不可访问的页面 {pages} 页；ugoira 动画 {ugoira} 个。它们不计入找到的图片数量。
"""


_WORDING_ROWS = r"""
Поиск изображений|Searching for images|正在查找图片
Поиск завершён|Search completed|查找完成
Продолжаем поиск|Continuing the search|继续查找
Поиск остановлен|Search stopped|查找已停止
Число изображений уточняется во время поиска; при скачивании показан прогресс текущего изображения.|The image count is updated during the search; downloading shows the current image's progress.|查找时会更新图片数量；下载时显示当前图片的进度。
Счётчик растёт во время поиска. Итог известен после завершения.|The count grows during the search. The final count is shown when the search finishes.|查找时数量会增加，完成后显示最终数量。
Счётчик растёт во время поиска. Итог доступных картинок известен после завершения.|The count grows during the search. The final available image count is shown on completion.|查找时数量会增加，完成后显示可获取图片的最终数量。
Ищем доступные изображения…\nСчётчик обновится по мере их обнаружения.|Searching for available images…\nThe count updates as images are found.|正在查找可获取的图片…\n找到图片后会更新数量。
Поиск завершён. Показано число доступных картинок в выбранных датах.|Search completed. The available image count for the selected dates is shown.|查找已完成。现已显示所选日期内可获取图片的数量。
Поиск завершён, часть файлов не скачана. Продолжите задание из истории, чтобы повторить попытку.|Search completed, but some files were not downloaded. Resume the job from history to retry.|查找已完成，但部分文件未下载。请从历史记录继续任务以重试。
Поиск изображений · уточняем количество|Searching for images · counting results|正在查找图片 · 正在统计数量
Продолжаем поиск · общее число ещё уточняется|Continuing the search · the total is still being determined|继续查找 · 总数仍在统计中
Поиск остановлен. Состояние сохранено.|Search stopped. State saved.|查找已停止，状态已保存。
Поиск остановлен · продолжение доступно в истории|Search stopped · resume from history|查找已停止 · 可从历史记录继续
Pixiv изменил формат ответа; поиск остановлен.|Pixiv changed its response format; the search stopped.|Pixiv 已更改响应格式，查找已停止。
Pixiv изменил формат публикации; поиск остановлен.|Pixiv changed its artwork format; the search stopped.|Pixiv 已更改作品数据格式，查找已停止。
Pixiv изменил формат страниц публикации; поиск остановлен.|Pixiv changed its artwork page format; the search stopped.|Pixiv 已更改作品页面格式，查找已停止。
Поиск завершён · найдено изображений: {count}|Search completed · images found: {count}|查找完成 · 找到图片：{count}
Поиск завершён с ошибками: найдено {count}, ошибок {errors}. Повторите для загрузки пропущенных.|Search completed with errors: {count} found, {errors} errors. Retry to download missing images.|查找已完成，但出现错误：找到 {count} 张图片，错误 {errors} 个。请重试以下载缺失图片。
"""

# Keep old worker/history messages readable when reopening an older collection.
# Only their displayed captions change; stored rows and state identifiers do not.
_WORDING_ALIASES = {
    "Обход медиагалереи": "Поиск изображений",
    "Обход уточняет число картинок; при скачивании показан прогресс текущего изображения.": "Число изображений уточняется во время поиска; при скачивании показан прогресс текущего изображения.",
    "Счётчик растёт при обходе. Итог известен после завершения.": "Счётчик растёт во время поиска. Итог известен после завершения.",
    "Счётчик растёт при обходе. Итог доступных картинок известен после завершения.": "Счётчик растёт во время поиска. Итог доступных картинок известен после завершения.",
    "Начинаем обход доступной медиагалереи…\nСчётчик обновится по мере обнаружения картинок.": "Ищем доступные изображения…\nСчётчик обновится по мере их обнаружения.",
    "Обход завершён. Показано число доступных картинок в выбранных датах.": "Поиск завершён. Показано число доступных картинок в выбранных датах.",
    "Обход завершён, часть файлов не скачана. Продолжите задание из истории, чтобы повторить попытку.": "Поиск завершён, часть файлов не скачана. Продолжите задание из истории, чтобы повторить попытку.",
    "Обход доступной медиагалереи · считаем изображения": "Поиск изображений · уточняем количество",
    "Продолжаем обход · общее число ещё уточняется": "Продолжаем поиск · общее число ещё уточняется",
    "Остановлено. Состояние сохранено.": "Поиск остановлен. Состояние сохранено.",
    "Остановлено · продолжение доступно в истории": "Поиск остановлен · продолжение доступно в истории",
    "Pixiv изменил формат ответа; обход остановлен.": "Pixiv изменил формат ответа; поиск остановлен.",
    "Pixiv изменил формат публикации; обход остановлен.": "Pixiv изменил формат публикации; поиск остановлен.",
    "Pixiv изменил формат страниц публикации; обход остановлен.": "Pixiv изменил формат страниц публикации; поиск остановлен.",
    "Доступный обход завершён · найдено изображений: {count}": "Поиск завершён · найдено изображений: {count}",
    "Обход завершён с ошибками: найдено {count}, ошибок {errors}. Повторите для загрузки пропущенных.": "Поиск завершён с ошибками: найдено {count}, ошибок {errors}. Повторите для загрузки пропущенных.",
}


def _rows(value):
    for line in value.strip().splitlines():
        if not line.strip():
            continue
        source, english, chinese = line.split("|", 2)
        yield tuple(part.replace(r"\n", "\n") for part in (source, english, chinese))


CATALOG = {source: {"en": english, "zh_CN": chinese} for source, english, chinese in _rows(_ROWS + _TEMPLATE_ROWS + _WORDING_ROWS)}
_REVERSE = {translation: source for source, translations in CATALOG.items() for translation in translations.values()}
for _old_source, _new_source in _WORDING_ALIASES.items():
    _REVERSE[_old_source] = _new_source
    for _old_translation in CATALOG[_old_source].values():
        _REVERSE[_old_translation] = _new_source
_DYNAMIC = []
for _source, _translations in CATALOG.items():
    if "{" not in _source:
        continue
    for _code, _template in (("ru", _source), *_translations.items()):
        _parts, _offset, _seen = [], 0, set()
        for _match in re.finditer(r"\{([A-Za-z_]\w*)\}", _template):
            _parts.append(re.escape(_template[_offset:_match.start()]))
            _name = _match[1]
            _parts.append(f"(?P={_name})" if _name in _seen else f"(?P<{_name}>.+?)")
            _seen.add(_name)
            _offset = _match.end()
        _parts.append(re.escape(_template[_offset:]))
        _specificity = len(re.sub(r"\{[A-Za-z_]\w*\}", "", _template))
        _DYNAMIC.append((re.compile("^" + "".join(_parts) + "$", re.DOTALL), _WORDING_ALIASES.get(_source, _source), _specificity))
_DYNAMIC.sort(key=lambda item: item[2], reverse=True)


def get_language() -> str:
    return _language


def calendar_locale_name() -> str:
    return {"ru": "ru_RU", "en": "en_US", "zh_CN": "zh_CN"}[_language]


def _install_qt_translation() -> None:
    global _qt_translator, _qt_language
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    from PySide6.QtWidgets import QApplication
    application = QApplication.instance()
    QLocale.setDefault(QLocale(calendar_locale_name()))
    if application is None or _qt_language == _language:
        return
    if _qt_translator is not None:
        application.removeTranslator(_qt_translator)
        _qt_translator = None
    if _language != "en":
        translator = QTranslator(application)
        directory = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if translator.load("qtbase_" + calendar_locale_name(), directory):
            application.installTranslator(translator)
            _qt_translator = translator
    _qt_language = _language


def set_language(code: str) -> None:
    global _language
    if code not in LANGUAGES:
        raise ValueError("Unsupported interface language")
    _language = code
    _install_qt_translation()


def tr(text: str, **values) -> str:
    """Translate a source caption or known completed status message.

    Unknown website text remains untouched. Dynamic captured values keep their
    numbers/platform/identifiers; known nested status messages are translated.
    """
    if not isinstance(text, str):
        return text
    source = _REVERSE.get(text, text)
    if source in CATALOG:
        translated = source if _language == "ru" else CATALOG[source][_language]
    else:
        translated = text
        for pattern, template, _ in _DYNAMIC:
            match = pattern.fullmatch(text)
            if match:
                arguments = match.groupdict()
                if "message" in arguments:
                    arguments["message"] = tr(arguments["message"])
                if "range" in arguments:
                    arguments["range"] = tr(arguments["range"])
                target = template if _language == "ru" else CATALOG[template][_language]
                translated = target.format(**arguments)
                break
    return translated.format(**values) if values else translated


translate = tr


def translate_message(value):
    """Translate UI event values recursively, without changing event keys."""
    if isinstance(value, str):
        return tr(value)
    if isinstance(value, dict):
        return {key: translate_message(item) for key, item in value.items()}
    if isinstance(value, list):
        return [translate_message(item) for item in value]
    if isinstance(value, tuple):
        return tuple(translate_message(item) for item in value)
    return value


_GETTERS = {"text": "text", "toolTip": "toolTip", "windowTitle": "windowTitle",
            "placeholderText": "placeholderText", "accessibleName": "accessibleName",
            "accessibleDescription": "accessibleDescription", "statusTip": "statusTip"}


def set_translated_property(widget, name: str, source: str) -> None:
    """Set a translated caption and retain its Russian source for live changes."""
    setter = getattr(widget, "set" + name[0].upper() + name[1:])
    source = _REVERSE.get(source, source)
    translated = tr(source)
    widget.setProperty("_mira_i18n_source_" + name, source)
    setter(translated)
    widget.setProperty("_mira_i18n_last_" + name, translated)


def set_translated_text(widget, source: str) -> None:
    set_translated_property(widget, "text", source)


def _translate_property(widget, name: str, getter, setter) -> None:
    current = getter()
    if not isinstance(current, str):
        return
    source_key, last_key = "_mira_i18n_source_" + name, "_mira_i18n_last_" + name
    source, last = widget.property(source_key), widget.property(last_key)
    if source is None or current != last:
        source = _REVERSE.get(current, current)
        widget.setProperty(source_key, source)
    translated = tr(source)
    setter(translated)
    widget.setProperty(last_key, translated)


def translate_widget_tree(root) -> None:
    """Translate captions live, preserving editable values and combo itemData."""
    from PySide6.QtCore import QLocale, Qt
    from PySide6.QtWidgets import (QAbstractButton, QCalendarWidget, QComboBox, QGroupBox,
                                  QLabel, QLineEdit, QTabWidget, QTableWidget, QTextEdit, QWidget)
    _install_qt_translation()
    objects = [root, *root.findChildren(QWidget)]
    for widget in objects:
        for name in ("toolTip", "windowTitle", "accessibleName", "accessibleDescription", "statusTip"):
            _translate_property(widget, name, getattr(widget, name), getattr(widget, "set" + name[0].upper() + name[1:]))
        if isinstance(widget, (QLabel, QAbstractButton)):
            _translate_property(widget, "text", widget.text, widget.setText)
        if isinstance(widget, (QLineEdit, QTextEdit)):
            _translate_property(widget, "placeholderText", widget.placeholderText, widget.setPlaceholderText)
        if isinstance(widget, QGroupBox):
            _translate_property(widget, "title", widget.title, widget.setTitle)
        if isinstance(widget, QComboBox) and not widget.property("_mira_i18n_skip_items"):
            for index in range(widget.count()):
                _translate_property(widget, f"combo_{index}", lambda i=index: widget.itemText(i),
                                    lambda value, i=index: widget.setItemText(i, value))
        if isinstance(widget, QTabWidget):
            for index in range(widget.count()):
                _translate_property(widget, f"tab_{index}", lambda i=index: widget.tabText(i),
                                    lambda value, i=index: widget.setTabText(i, value))
        if isinstance(widget, QTableWidget):
            for column in range(widget.columnCount()):
                item = widget.horizontalHeaderItem(column)
                if item is None:
                    continue
                source_role, last_role = int(Qt.ItemDataRole.UserRole) + 1001, int(Qt.ItemDataRole.UserRole) + 1002
                source, last = item.data(source_role), item.data(last_role)
                if source is None or item.text() != last:
                    source = _REVERSE.get(item.text(), item.text())
                    item.setData(source_role, source)
                item.setText(tr(source))
                item.setData(last_role, item.text())
                if source == "Статус":
                    for row in range(widget.rowCount()):
                        status = widget.item(row, column)
                        if status is not None:
                            status_source = status.data(source_role)
                            if status_source is None or status.text() != status.data(last_role):
                                status_source = _REVERSE.get(status.text(), status.text())
                                status.setData(source_role, status_source)
                            status.setText(tr(status_source))
                            status.setData(last_role, status.text())
        if isinstance(widget, QCalendarWidget):
            widget.setLocale(QLocale(calendar_locale_name()))
            refresh = getattr(widget.parent(), "_update_header", None)
            if callable(refresh):
                refresh(widget.yearShown(), widget.monthShown())


def localized_help_html(source_html: str = "") -> str:
    if _language == "ru":
        return source_html
    if _language == "en":
        return """<h3>1. Choose a creator</h3><p>Paste an X / Twitter profile URL (https://x.com/username) or a Pixiv creator URL (https://www.pixiv.net/users/123). The platform is detected automatically; choosing another platform clears a conflicting URL. Pixiv support is experimental.</p>
<h3>2. Choose where and what to save</h3><p>Choose a folder. Originals are saved under platform / numeric creator ID, so a renamed account keeps the same folder. <b>All dates</b> opens a calendar filter with either or both date bounds. Dates are inclusive and use UTC. <b>Apply</b> commits changes; <b>Cancel</b> keeps the previous range.</p>
<p><b>Find and download</b> finds, counts and saves images as they are discovered. <b>Find and count</b> is an optional preview without downloading originals. Each image in a post counts separately; the final total is known when the search finishes. Thumbnails appear for saved files. Videos and Pixiv ugoira animations are skipped.</p>
<p><b>New images only</b> uses local history to skip saved files; duplicate contents are detected. Availability and the highest returned resolution depend on the platform.</p>
<h3>3. Sign in</h3><p>Click <b>Sign in to X</b> or <b>Sign in to Pixiv</b>. Enter passwords and verification codes only on the official website. Complete its checks, then click <b>Save sign-in</b>. Pixiv checks your account automatically, including on English and settings pages. Click <b>Check sign-in</b> to retry; Save requires a fresh successful check. A guest session is insufficient. The app does not read form contents or passwords.</p>
<p>The login browser uses a temporary profile. Only the minimal session is saved, encrypted with Windows protection for your user account. Cancelling leaves an earlier saved session intact. Sign-out removes only the selected platform's local Mira session; revoke other sessions on the platform itself.</p>
<p>External Google/Apple login and Windows Hello passkeys are not supported in this embedded window. Use the platform's password flow and complete any required two-factor checks yourself. Mira does not bypass access checks. Websites may restrict embedded browsers.</p>
<p>For Pixiv, adjust your account's <a href="https://www.pixiv.net/settings/viewing">viewing settings</a> yourself before downloading the content you need. Mira respects account access and cannot guarantee all content.</p>
<h3>Other sign-in methods and request limits</h3><p><b>Advanced</b> contains browser import, your own Netscape cookies.txt file, local sign-out and the request interval. Firefox's ordinary profile session is recommended; containers are not supported. Chrome, Edge or Brave may prevent protected-session import. Mira does not bypass this protection or silently switch to anonymous access. Keep cookie files private, like passwords. Credentials are not sent to third-party services or included in settings or logs.</p>
<h3>Pause, stop and resume</h3><p>Pause and stop take effect after the current operation. Checkpoints, history and logs are stored in the collection's hidden <b>.mira</b> folder. Keep this folder to resume jobs from <b>History</b>. Recheck sign-in when resuming; select a cookie file again if needed.</p>
<h3>Access and interface settings</h3><p>Use content within your rights and platform rules. Private, deleted, regional or otherwise restricted posts may be unavailable, and platforms can return incomplete history even after sign-in. Increase the request interval and retry later if rate-limited. The header offers language and light/dark theme choices; changing them does not restart a download.</p>"""
    return """<h3>1. 选择作者</h3><p>粘贴 X / Twitter 主页链接（https://x.com/username）或 Pixiv 作者链接（https://www.pixiv.net/users/123）。应用会自动识别平台；手动切换平台时会清除不匹配的链接。Pixiv 支持仍处于实验阶段。</p>
<h3>2. 选择保存位置及内容</h3><p>选择文件夹。原图按“平台 / 作者数字 ID”保存，作者改名后仍使用同一文件夹。<b>所有日期</b>打开日历筛选器，可只设置一个日期边界或同时设置两个。起止日期均包含在内，日期按 UTC 计算。<b>应用</b>保存选择；<b>取消</b>保留原范围。</p>
<p><b>查找并下载</b>会在查找图片时统计并保存结果。<b>查找并统计</b>仅预览，不下载原图。帖子中的每张图片分别计数，查找完成后显示最终数量。已保存的文件可显示缩略图。视频及 Pixiv ugoira 动画会被跳过。</p>
<p><b>仅下载新图片</b>使用本地历史记录跳过已保存的文件，并检测重复内容。可获取的图片及最高画质取决于平台返回的结果。</p>
<h3>3. 登录</h3><p>点击<b>登录 X</b>或<b>登录 Pixiv</b>，仅在官方网站页面中输入密码和验证码。完成网站验证后点击<b>保存登录状态</b>。Pixiv 会自动验证账号登录，包括英语页面和设置页面。点击<b>检查登录状态</b>可重试；保存前必须重新验证成功。访客会话无效。应用不会读取表单内容或密码。</p>
<p>登录窗口使用临时浏览器配置。应用仅保存必要的会话数据，并使用当前 Windows 用户的保护机制加密。取消不会覆盖此前保存的登录状态。退出登录只会删除 Mira 在本机保存的所选平台会话；如需撤销其他会话，请到平台设置中操作。</p>
<p>应用内窗口不支持 Google、Apple 等外部登录，也不支持 Windows Hello 通行密钥。请使用平台密码登录，并自行完成所需的双重验证。Mira 不会绕过访问验证。网站也可能限制应用内浏览器。</p>
<p>下载 Pixiv 内容前，请自行调整账号的<a href="https://www.pixiv.net/settings/viewing">显示设置</a>。Mira 遵守账号访问权限，无法保证获取全部内容。</p>
<h3>其他登录方式及请求间隔</h3><p><b>更多设置</b>包含浏览器会话导入、自己的 Netscape cookies.txt 文件、本地退出登录以及请求间隔。推荐使用 Firefox 普通配置文件，不支持容器。Chrome、Edge 或 Brave 可能禁止读取受保护会话。Mira 不会绕过此保护，也不会自动转为匿名访问。请像保管密码一样保管 cookies 文件。凭据不会发送到第三方服务，也不会写入设置或日志。</p>
<h3>暂停、停止与继续</h3><p>暂停及停止会在当前操作完成后生效。检查点、历史记录和日志保存在收藏文件夹的隐藏 <b>.mira</b> 目录中。请保留此目录，以便从<b>历史记录</b>继续任务。继续前请检查登录状态；必要时重新选择 cookies 文件。</p>
<h3>访问限制及界面设置</h3><p>请在自身权利及平台规则允许的范围内使用内容。私密、已删除、地区限制或其他受限帖子可能不可获取；即使登录成功，平台也可能返回不完整历史。遇到请求限制时，请增大间隔并稍后重试。窗口顶部可选择语言及浅色/深色主题，切换不会重新启动下载任务。</p>"""
