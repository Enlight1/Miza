print = PRINT

try:
    import googletrans
except:
    print_exc()
    googletrans = None
import convobot

try:
    rapidapi_key = AUTH["rapidapi_key"]
    if not rapidapi_key:
        raise
except:
    rapidapi_key = None
    print("WARNING: rapidapi_key not found. Unable to search Urban Dictionary.")


class Translate(Command):
    time_consuming = True
    name = ["TR"]
    description = "Translates a string into another language."
    usage = "<0:language(en)>? <1:string>"
    flags = "v"
    no_parse = True
    rate_limit = (2, 7)
    slash = True
    if googletrans:
        languages = demap(googletrans.LANGUAGES)
        trans = googletrans.Translator()
        trans.client.headers["DNT"] = "1"

    async def __call__(self, channel, argv, user, message, **void):
        if not googletrans:
            raise RuntimeError("Unable to load Google Translate.")
        if not argv:
            raise ArgumentError("Input string is empty.")
        self.trans.client.headers["X-Forwarded-For"] = ".".join(str(xrand(1, 255)) for _ in loop(4))
        try:
            lang, arg = argv.split(None, 1)
        except ValueError:
            lang = "en"
            arg = argv
        else:
            if lang.casefold() not in self.languages:
                arg = argv
                lang = "en"
        resp = await create_future(self.trans.translate, arg, dest=lang)
        footer = dict(text=f"Detected language: {resp.src}")
        if getattr(resp, "pronunciation", None):
            fields = (("Pronunciation", resp.pronunciation),)
        else:
            fields = None
        self.bot.send_as_embeds(channel, resp.text, fields=fields, author=get_author(user), footer=footer, reference=message)


class Math(Command):
    _timeout_ = 4
    name = ["🔢", "M", "PY", "Sympy", "Plot", "Calc"]
    alias = name + ["Plot3D", "Factor", "Factorise", "Factorize"]
    description = "Evaluates a math formula."
    usage = "<string> <verbose{?v}>? <rationalize{?r}>? <show_variables{?l}>? <clear_variables{?c}>?"
    flags = "rvlcd"
    rate_limit = (0.5, 5)
    slash = True

    async def __call__(self, bot, argv, name, message, channel, guild, flags, user, **void):
        if argv == "69":
            return py_md("69 = nice")
        if "l" in flags:
            var = bot.data.variables.get(user.id, {})
            if not var:
                return ini_md(f"No currently assigned variables for {sqr_md(user)}.")
            return f"Currently assigned variables for {user}:\n" + ini_md(iter2str(var))
        if "c" in flags or "d" in flags:
            bot.data.variables.pop(user.id, None)
            return italics(css_md(f"Successfully cleared all variables for {sqr_md(user)}."))
        if not argv:
            raise ArgumentError(f"Input string is empty. Use {bot.get_prefix(guild)}math help for help.")
        r = "r" in flags
        p = flags.get("v", 0) * 2 + 1 << 7
        var = None
        if "plot" in name and not argv.lower().startswith("plot") or "factor" in name:
            argv = f"{name}({argv})"
        elif name.startswith("m"):
            for equals in ("=", ":="):
                if equals in argv:
                    ii = argv.index(equals)
                    for i, c in enumerate(argv):
                        if i >= ii:
                            temp = argv[i + len(equals):]
                            if temp.startswith("="):
                                break
                            check = argv[:i].strip().replace(" ", "")
                            if check.isnumeric():
                                break
                            var = check
                            argv = temp.strip()
                            break
                        elif not (c.isalnum() or c in " _"):
                            break
                    if var is not None:
                        break
        resp = await bot.solve_math(argv, p, r, timeout=24, variables=bot.data.variables.get(user.id))
        # Determine whether output is a direct answer or a file
        if type(resp) is dict and "file" in resp:
            await channel.trigger_typing()
            fn = resp["file"]
            f = CompatFile(fn)
            await bot.send_with_file(channel, "", f, filename=fn, best=True, reference=message)
            return
        answer = "\n".join(str(i) for i in resp)
        if var is not None:
            env = bot.data.variables.setdefault(user.id, {})
            env[var] = resp[0]
            while len(env) > 64:
                env.pop(next(iter(env)))
            bot.data.variables.update(user.id)
            return css_md(f"Variable {sqr_md(var)} set to {sqr_md(resp[0])}.")
        if argv.lower() == "help":
            return answer
        return py_md(f"{argv} = {answer}")


class UpdateVariables(Database):
    name = "variables"


class Unicode(Command):
    name = [
        "Uni2Hex", "U2H", "HexEncode",
        "Hex2Uni", "H2U", "HexDecode",
        "Uni2Bin", "U2B", "BinEncode",
        "Bin2Uni", "B2U", "BinDecode",
        "Uni2B64", "U64", "B64Encode",
        "B642Uni", "64U", "B64Decode",
        "Uni2B32", "U32", "B32Encode",
        "B322Uni", "32U", "B32Decode",
    ]
    description = "Converts unicode text to hexadecimal or binary numbers."
    usage = "<string>"
    no_parse = True

    def __call__(self, argv, name, **void):
        if not argv:
            raise ArgumentError("Input string is empty.")
        if name in ("uni2hex", "u2h", "hexencode"):
            b = bytes2hex(argv.encode("utf-8"))
            return fix_md(b)
        if name in ("hex2uni", "h2u", "hexdecode"):
            b = as_str(hex2bytes(to_alphanumeric(argv).replace("0x", "")))
            return fix_md(b)
        if name in ("uni2bin", "u2b", "binencode"):
            b = " ".join(f"{ord(c):08b}" for c in argv)
            return fix_md(b)
        if name in ("bin2uni", "b2u", "bindecode"):
            b = to_alphanumeric(argv).replace("0x", "").replace(" ", "").encode("ascii")
            b = (np.frombuffer(b, dtype=np.uint8) - 48).astype(bool)
            if len(b) & 7:
                a = np.zeros(8 - len(b) % 8, dtype=bool)
                if len(b) < 8:
                    b = np.append(a, b)
                else:
                    b = np.append(b, a)
            a = np.zeros(len(b) >> 3, dtype=np.uint8)
            for i in range(8):
                c = b[i::8]
                if i < 7:
                    c = c.astype(np.uint8)
                    c <<= 7 - i
                a += c
            b = as_str(a.tobytes())
            return fix_md(b)
        if name in ("uni2b64", "u64", "b64encode"):
            b = as_str(base64.b64encode(argv.encode("utf-8")).rstrip(b"="))
            return fix_md(b)
        if name in ("b642uni", "64u", "b64decode"):
            b = unicode_prune(argv).encode("utf-8") + b"=="
            if (len(b) - 1) & 3 == 0:
                b += b"="
            b = as_str(base64.b64decode(b))
            return fix_md(b)
        if name in ("uni2b32", "u32", "b32encode"):
            b = as_str(base64.b32encode(argv.encode("utf-8")).rstrip(b"="))
            return fix_md(b)
        if name in ("b322uni", "32u", "b32decode"):
            b = unicode_prune(argv).encode("utf-8")
            if len(b) & 7:
                b += b"=" * (8 - len(b) % 8)
            b = as_str(base64.b32decode(b))
            return fix_md(b)
        b = shash(argv)
        return fix_md(b)


class ID2Time(Command):
    name = ["I2T", "CreateTime", "Timestamp", "Time2ID", "T2I"]
    description = "Converts a discord ID to its corresponding UTC time."
    usage = "<string>"

    def __call__(self, argv, name, **void):
        if not argv:
            raise ArgumentError("Input string is empty.")
        if name in ("time2id", "t2i"):
            argv = tzparse(argv)
            s = time_snowflake(argv)
        else:
            argv = int(verify_id("".join(c for c in argv if c.isnumeric() or c == "-")))
            s = snowflake_time(argv)
        return fix_md(s)


class Fancy(Command):
    name = ["FancyText"]
    description = "Creates translations of a string using unicode fonts."
    usage = "<string>"
    no_parse = True
    slash = True

    def __call__(self, channel, argv, message, **void):
        if not argv:
            raise ArgumentError("Input string is empty.")
        fields = deque()
        for i in range(len(UNIFMTS) - 1):
            s = uni_str(argv, i)
            if i == len(UNIFMTS) - 2:
                s = s[::-1]
            fields.append((f"Font {i + 1}", s + "\n"))
        self.bot.send_as_embeds(channel, fields=fields, author=dict(name=lim_str(argv, 256)), reference=message)


class Zalgo(Command):
    name = ["Chaos", "ZalgoText"]
    description = "Generates random combining accent symbols between characters in a string."
    usage = "<string>"
    no_parse = True
    slash = True
    chrs = [chr(n) for n in zalgo_map]
    randz = lambda self: choice(self.chrs)
    def zalgo(self, s, x):
        if unfont(s) == s:
            return "".join(c + self.randz() for c in s)
        return s[0] + "".join("".join(self.randz() + "\u200b" for i in range(x + 1 >> 1)) + c + "\u200a" + "".join(self.randz() + "\u200b" for i in range(x >> 1)) for c in s[1:])

    async def __call__(self, channel, argv, message, **void):
        if not argv:
            raise ArgumentError("Input string is empty.")
        fields = deque()
        for i in range(1, 9):
            s = self.zalgo(argv, i)
            fields.append((f"Level {i}", s + "\n"))
        self.bot.send_as_embeds(channel, fields=fields, author=dict(name=lim_str(argv, 256)), reference=message)


class Format(Command):
    name = ["FormatText"]
    description = "Creates neatly fomatted text using combining unicode characters."
    usage = "<string>"
    no_parse = True
    slash = True
    formats = "".join(chr(i) for i in (0x30a, 0x325, 0x303, 0x330, 0x30c, 0x32d, 0x33d, 0x353, 0x35b, 0x20f0))

    def __call__(self, channel, argv, message, **void):
        if not argv:
            raise ArgumentError("Input string is empty.")
        fields = deque()
        for i, f in enumerate(self.formats):
            s = "".join(c + f for c in argv)
            fields.append((f"Format {i}", s + "\n"))
        s = "".join("_" if c in " _" else c if c in "gjpqy" else c + chr(818) for c in argv)
        fields.append((f"Format {i + 1}", s))
        self.bot.send_as_embeds(channel, fields=fields, author=dict(name=lim_str(argv, 256)), reference=message)


class UnFancy(Command):
    name = ["UnFormat", "UnZalgo"]
    description = "Removes unicode formatting and diacritic characters from inputted text."
    usage = "<string>"
    slash = True

    def __call__(self, argv, **void):
        if not argv:
            raise ArgumentError("Input string is empty.")
        return fix_md(argv)


class OwOify(Command):
    omap = {
        "r": "w",
        "R": "W",
        "l": "w",
        "L": "W",
    }
    otrans = "".maketrans(omap)
    name = ["UwU", "OwO", "UwUify"]
    description = "Applies the owo/uwu text filter to a string."
    usage = "<string> <aggressive{?a}>? <basic{?b}>?"
    flags = "ab"
    no_parse = True

    def __call__(self, argv, flags, **void):
        if not argv:
            raise ArgumentError("Input string is empty.")
        out = argv.translate(self.otrans)
        temp = None
        if "a" in flags:
            out = out.replace("v", "w").replace("V", "W")
        if "a" in flags or "b" not in flags:
            temp = list(out)
            for i, c in enumerate(out):
                if i > 0 and c in "yY" and out[i - 1].casefold() not in "aeioucdhvwy \n\t":
                    if c.isupper():
                        temp[i] = "W" + c.casefold()
                    else:
                        temp[i] = "w" + c
                if i < len(out) - 1 and c in "nN" and out[i + 1].casefold() in "aeiou":
                    temp[i] = c + "y"
            if "a" in flags and "b" not in flags:
                out = "".join(temp)
                temp = list(out)
                for i, c in enumerate(out):
                    if i > 0 and c.casefold() in "aeiou" and out[i - 1].casefold() not in "aeioucdhvwy \n\t":
                        if c.isupper():
                            temp[i] = "W" + c.casefold()
                        else:
                            temp[i] = "w" + c
        if temp is not None:
            out = "".join(temp)
            if "a" in flags:
                for c in " \n\t":
                    if c in out:
                        spl = out.split(c)
                        for i, w in enumerate(spl):
                            if w.casefold().startswith("th"):
                                spl[i] = ("D" if w[0].isupper() else "d") + w[2:]
                            elif "th" in w:
                                spl[i] = w.replace("th", "ff")
                        out = c.join(spl)
        return fix_md(out)


class AltCaps(Command):
    description = "Alternates the capitalization on characters in a string."
    usage = "<string>"
    no_parse = True

    def __call__(self, argv, **void):
        if not argv:
            raise ArgumentError("Input string is empty.")
        i = argv[0].isupper()
        a = argv[i::2].casefold()
        b = argv[1 - i::2].upper()
        if i:
            a, b = b, a
        if len(a) > len(b):
            c = a[-1]
            a = a[:-1]
        else:
            c = ""
        return fix_md("".join(i[0] + i[1] for i in zip(a, b)) + c)


class Say(Command):
    description = "Repeats a message that the user provides."
    usage = "<string>"
    no_parse = True
    slash = True
    
    def __call__(self, bot, user, message, argv, **void):
        create_task(bot.silent_delete(message, no_log=-1))
        if not argv:
            raise ArgumentError("Input string is empty.")
        if not bot.is_owner(user):
            argv = lim_str("\u200b" + escape_roles(argv).lstrip("\u200b"), 2000)
        create_task(message.channel.send(argv))


# Char2Emoj, a simple script to convert a string into a block of text
def _c2e(string, em1, em2):
    chars = {
        " ": [0, 0, 0, 0, 0],
        "_": [0, 0, 0, 0, 7],
        "!": [2, 2, 2, 0, 2],
        '"': [5, 5, 0, 0, 0],
        ":": [0, 2, 0, 2, 0],
        ";": [0, 2, 0, 2, 4],
        "~": [0, 5, 7, 2, 0],
        "#": [10, 31, 10, 31, 10],
        "$": [7, 10, 6, 5, 14],
        "?": [6, 1, 2, 0, 2],
        "%": [5, 1, 2, 4, 5],
        "&": [4, 10, 4, 10, 7],
        "'": [2, 2, 0, 0, 0],
        "(": [2, 4, 4, 4, 2],
        ")": [2, 1, 1, 1, 2],
        "[": [6, 4, 4, 4, 6],
        "]": [3, 1, 1, 1, 3],
        "|": [2, 2, 2, 2, 2],
        "*": [21, 14, 4, 14, 21],
        "+": [0, 2, 7, 2, 0],
        "=": [0, 7, 0, 7, 0],
        ",": [0, 0, 3, 3, 4],
        "-": [0, 0, 7, 0, 0],
        ".": [0, 0, 3, 3, 0],
        "/": [1, 1, 2, 4, 4],
        "\\": [4, 4, 2, 1, 1],
        "@": [14, 17, 17, 17, 14],
        "0": [7, 5, 5, 5, 7],
        "1": [3, 1, 1, 1, 1],
        "2": [7, 1, 7, 4, 7],
        "3": [7, 1, 7, 1, 7],
        "4": [5, 5, 7, 1, 1],
        "5": [7, 4, 7, 1, 7],
        "6": [7, 4, 7, 5, 7],
        "7": [7, 5, 1, 1, 1],
        "8": [7, 5, 7, 5, 7],
        "9": [7, 5, 7, 1, 7],
        "A": [2, 5, 7, 5, 5],
        "B": [6, 5, 7, 5, 6],
        "C": [3, 4, 4, 4, 3],
        "D": [6, 5, 5, 5, 6],
        "E": [7, 4, 7, 4, 7],
        "F": [7, 4, 7, 4, 4],
        "G": [7, 4, 5, 5, 7],
        "H": [5, 5, 7, 5, 5],
        "I": [7, 2, 2, 2, 7],
        "J": [7, 1, 1, 5, 7],
        "K": [5, 5, 6, 5, 5],
        "L": [4, 4, 4, 4, 7],
        "M": [17, 27, 21, 17, 17],
        "N": [9, 13, 15, 11, 9],
        "O": [2, 5, 5, 5, 2],
        "P": [7, 5, 7, 4, 4],
        "Q": [4, 10, 10, 10, 5],
        "R": [6, 5, 7, 6, 5],
        "S": [3, 4, 7, 1, 6],
        "T": [7, 2, 2, 2, 2],
        "U": [5, 5, 5, 5, 7],
        "V": [5, 5, 5, 5, 2],
        "W": [17, 17, 21, 21, 10],
        "X": [5, 5, 2, 5, 5],
        "Y": [5, 5, 2, 2, 2],
        "Z": [7, 1, 2, 4, 7],
    }
    # I don't quite remember how this algorithm worked lol
    printed = ["\u200b"] * 7
    string = string.upper()
    for i in range(len(string)):
        curr = string[i]
        data = chars.get(curr, [15] * 5)
        size = max(1, max(data))
        lim = max(2, int(log(size, 2))) + 1
        printed[0] += em2 * (lim + 1)
        printed[6] += em2 * (lim + 1)
        if len(data) == 5:
            for y in range(5):
                printed[y + 1] += em2
                for p in range(lim):
                    if data[y] & (1 << (lim - 1 - p)):
                        printed[y + 1] += em1
                    else:
                        printed[y + 1] += em2
        for x in range(len(printed)):
            printed[x] += em2
    return printed


class Char2Emoji(Command):
    name = ["C2E", "Char2Emoj"]
    description = "Makes emoji blocks using a string."
    usage = "<0:string> <1:emoji_1> <2:emoji_2>"
    no_parse = True
    slash = True

    def __call__(self, args, guild, message, **extra):
        if len(args) != 3:
            raise ArgumentError(
                "Exactly 3 arguments are required for this command.\n"
                + "Place quotes around arguments containing spaces as required."
            )
        webhook = not getattr(guild, "ghost", None)
        for i, a in enumerate(args):
            e_id = None
            if find_emojis(a):
                e_id = a.rsplit(":", 1)[-1].rstrip(">")
                ani = a.startswith("<a:")
            elif a.isnumeric():
                e_id = a = int(a)
                try:
                    a = self.bot.cache.emojis[a]
                except KeyError:
                    ani = False
                else:
                    ani = a.animated
            if e_id:
                # if int(e_id) not in (e.id for e in guild.emojis):
                #     webhook = False
                if ani:
                    args[i] = f"<a:_:{e_id}>"
                else:
                    args[i] = f"<:_:{e_id}>"
        resp = _c2e(*args[:3])
        if hasattr(message, "simulated"):
            return resp
        out = []
        for line in resp:
            if not out or len(out[-1]) + len(line) + 1 > 2000:
                out.append(line)
            else:
                out[-1] += "\n" + line
        if len(out) <= 3:
            out = ["\n".join(i) for i in (resp[:2], resp[2:5], resp[5:])]
        if webhook:
            out = alist(out)
        return out


class EmojiCrypt(Command):
    name = ["EncryptEmoji", "DecryptEmoji", "EmojiEncrypt", "EmojiDecrypt"]
    description = "Encrypts the input text or file into smileys."
    usage = "<string> <encrypt{?e}|decrypt{?d}> <encrypted{?p}>? <-1:password>"
    no_parse = True
    slash = True
    flags = "ed"

    async def __call__(self, args, name, flags, message, **extra):
        password = None
        for flag in ("+p", "-p", "?p"):
            try:
                i = args.index(flag)
            except ValueError:
                continue
            password = args[i + 1]
            args = args[:i] + args[i + 2:]
        msg = " ".join(args)
        fi = f"cache/temp-{ts_us()}"
        if not msg:
            msg = message.attachments[0].url
        if is_url(msg):
            msg = await self.bot.follow_url(msg, allow=True, limit=1)
            args = (python, "downloader.py", msg, "../" + fi)
            proc = await asyncio.create_subprocess_exec(*args, cwd="misc")
            try:
                await asyncio.wait_for(proc.wait(), timeout=48)
            except (T0, T1, T2):
                with tracebacksuppressor:
                    force_kill(proc)
                raise
        else:
            with open(fi, "w", encoding="utf-8") as f:
                await create_future(f.write, msg)
        fs = os.path.getsize(fi)
        args = [python, "neutrino.py", "-y", "../" + fi, "../" + fi + "-"]
        if "d" in flags or "decrypt" in name:
            args.append("--decrypt")
        else:
            c = round_random(27 - math.log(fs, 2))
            c = max(min(c, 9), 0)
            args.extend((f"-c{c}", "--encrypt"))
        args.append(password or "\x7f")
        proc = await asyncio.create_subprocess_exec(*args, cwd="misc")
        try:
            await asyncio.wait_for(proc.wait(), timeout=60)
        except (T0, T1, T2):
            with tracebacksuppressor:
                force_kill(proc)
            raise
        fn = "message.txt"
        f = CompatFile(fi + "-", filename=fn)
        return dict(file=f, filename=fn)


class Time(Command):
    name = ["🕰️", "⏰", "⏲️", "UTC", "GMT", "T", "EstimateTime", "EstimateTimezone"]
    description = "Shows the current time at a certain GMT/UTC offset, or the current time for a user. Be sure to check out ⟨WEBSERVER⟩/time!"
    usage = "<offset_hours|user>?"
    slash = True

    async def __call__(self, name, channel, guild, argv, args, user, **void):
        u = user
        s = 0
        # Only check for timezones if the command was called with alias "estimate_time", "estimate_timezone", "t", or "time"
        if "estimate" in name:
            if argv:
                try:
                    if not argv.isnumeric():
                        raise KeyError
                    user = self.bot.cache.guilds[int(argv)]
                except KeyError:
                    try:
                        user = self.bot.cache.channels[verify_id(argv)]
                    except KeyError:
                        user = await self.bot.fetch_user_member(argv, guild)
            argv = None
        if args and name in "time":
            try:
                i = None
                with suppress(ValueError):
                    i = argv.index("-")
                with suppress(ValueError):
                    j = argv.index("+")
                    if i is None:
                        i = j
                    else:
                        i = min(i, j)
                if i is not None:
                    s = as_timezone(argv[:i])
                    argv = argv[i:]
                else:
                    s = as_timezone(argv)
                    argv = "0"
            except KeyError:
                user = await self.bot.fetch_user_member(argv, guild)
                argv = None
        elif name in TIMEZONES:
            s = TIMEZONES.get(name, 0)
        estimated = None
        if argv:
            h = await self.bot.eval_math(argv)
        elif "estimate" in name:
            if is_channel(user):
                h = self.bot.data.users.estimate_timezone("#" + str(user.id))
            else:
                h = self.bot.data.users.estimate_timezone(user.id)
            estimated = True
        elif name in "time":
            h = self.bot.data.users.get_timezone(user.id)
            if h is None:
                h = self.bot.data.users.estimate_timezone(user.id)
                estimated = True
            else:
                estimated = False
        else:
            h = 0
        hrs = round_min(h + s / 3600)
        if hrs:
            if abs(hrs) > 17531640:
                t = utc_ddt()
                t += hrs * 3600
            else:
                t = utc_dt()
                t += datetime.timedelta(hours=hrs)
        else:
            t = utc_dt()
        if hrs >= 0:
            hrs = "+" + str(hrs)
        out = f"Current time at UTC/GMT{hrs}: {sqr_md(t)}."
        if estimated:
            out += f"\nUsing timezone automatically estimated from {sqr_md(user)}'s discord activity."
        elif estimated is not None:
            out += f"\nUsing timezone assigned by {sqr_md(user)}."
        return ini_md(out)


class Timezone(Command):
    description = "Shows the current time in a certain timezone. Be sure to check out ⟨WEBSERVER⟩/time!"
    usage = "<timezone> <list{?l}>?"

    async def __call__(self, channel, argv, message, **void):
        if not argv:
            return await self.bot.commands.time[0]("timezone", channel, channel.guild, "", [], message.author)
        if argv.startswith("-l") or argv.startswith("list"):
            fields = deque()
            for k, v in COUNTRIES.items():
                fields.append((k, ", ".join(v), False))
            self.bot.send_as_embeds(channel, description=f"[Click here to find your timezone]({self.bot.webserver}/time)", title="Timezone list", fields=fields, author=get_author(self.bot.user), reference=message)
            return
        secs = as_timezone(argv)
        t = utc_dt() + datetime.timedelta(seconds=secs)
        h = round_min(secs / 3600)
        if not h < 0:
            h = "+" + str(h)
        return ini_md(f"Current time at UTC/GMT{h}: {sqr_md(t)}.")


class TimeCalc(Command):
    name = ["TimeDifference", "TimeDiff", "TimeSum", "TimeAdd"]
    description = "Computes the sum or difference between two times, or the Unix timestamp of a datetime string."
    usage = "<0:time1> [|,] <1:time2>?"
    no_parse = True

    def __call__(self, argv, user, name, **void):
        if not argv:
            timestamps = [utc()]
        else:
            if "|" in argv:
                spl = argv.split("|")
            elif "," in argv:
                spl = argv.split(",")
            else:
                spl = [argv]
            timestamps = [utc_ts(tzparse(t)) for t in spl]
        if len(timestamps) == 1:
            out = f"{round_min(timestamps[0])} ({DynamicDT.utcfromtimestamp(timestamps[0])} UTC)"
        elif "sum" not in name and "add" not in name:
            out = dyn_time_diff(max(timestamps), min(timestamps))
        else:
            out = time_sum(*timestamps)
        return code_md(out)


class Identify(Command):
    name = ["📂", "Magic", "Mime", "FileType"]
    description = "Detects the type, mime, and optionally details of an input file."
    usage = "<url>*"
    rate_limit = (2, 7)
    mime = magic.Magic(mime=True, mime_encoding=True)
    msgcmd = True
    slash = True

    def probe(self, url):
        command = ["./ffprobe", "-hide_banner", url]
        resp = None
        for _ in loop(3):
            try:
                proc = psutil.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                fut = create_future_ex(proc.communicate, timeout=12)
                res = fut.result(timeout=12)
                resp = b"\n".join(res)
                break
            except:
                with suppress():
                    force_kill(proc)
                print_exc()
        if not resp:
            raise RuntimeError
        return as_str(resp)

    def identify(self, url):
        out = deque()
        with reqs.next().get(url, headers=Request.header(), stream=True) as resp:
            head = fcdict(resp.headers)
            it = resp.iter_content(262144)
            data = next(it)
        out.append(code_md(magic.from_buffer(data)))
        mimedata = self.mime.from_buffer(data).replace("; ", "\n")
        mime = mimedata.split("\n", 1)[0].split("/", 1)
        if mime == ["text", "plain"]:
            if "Content-Type" in head:
                ctype = head["Content-Type"]
                spl = ctype.split("/")
                if spl[-1].casefold() != "octet-stream":
                    mimedata = ctype + "\n" + mimedata.split("\n", 1)[-1]
                    mime = spl
        mimedata = "mimetype: " + mimedata
        if "Content-Length" in head:
            fs = head['Content-Length']
        elif len(data) < 131072:
            fs = len(data)
        else:
            fs = None
        if fs is not None:
            mimedata = f"filesize: {byte_scale(int(fs))}B\n" + mimedata
        out.append(fix_md(mimedata))
        with tracebacksuppressor:
            resp = self.probe(url)
            if mime[0] == "image" and mime[1] != "gif":
                search = "Video:"
                spl = regexp(r"\([^)]+\)").sub("", resp[resp.index(search) + len(search):].split("\n", 1)[0].strip()).strip().split(", ")
                out.append(code_md(f"Codec: {spl[1]}\nSize: {spl[2].split(None, 1)[0]}"))
            elif mime[0] == "video" or mime[1] == "gif":
                search = "Duration:"
                resp = resp[resp.index(search) + len(search):]
                dur = time_disp(time_parse(resp[:resp.index(",")]), False)
                search = "bitrate:"
                resp = resp[resp.index(search) + len(search):]
                bps = resp.split("\n", 1)[0].strip().rstrip("b/s").casefold()
                mult = 1
                if bps.endswith("k"):
                    mult = 10 ** 3
                elif bps.endswith("m"):
                    mult = 10 ** 6
                elif bps.endswith("g"):
                    mult = 10 ** 9
                bps = byte_scale(int(bps.split(None, 1)[0]) * mult, ratio=1000) + "bps"
                s = f"Duration: {dur}\nBitrate: {bps}"
                search = "Video:"
                try:
                    resp = resp[resp.index(search) + len(search):]
                except ValueError:
                    pass
                else:
                    spl = regexp(r"\([^)]+\)").sub("", resp.split("\n", 1)[0].strip()).strip().split(", ")
                    s += f"\nCodec: {spl[1]}\nSize: {spl[2].split(None, 1)[0]}"
                    for i in spl[3:]:
                        if i.endswith(" fps"):
                            s += f"\nFPS: {i[:-4]}"
                            break
                out.append(code_md(s))
                search = "Audio:"
                try:
                    resp = resp[resp.index(search) + len(search):]
                except ValueError:
                    pass
                else:
                    spl = regexp(r"\([^)]+\)").sub("", resp.split("\n", 1)[0].strip()).strip().split(", ")
                    fmt = spl[0]
                    sr = spl[1].split(None, 1)[0]
                    s = f"Audio format: {fmt}\nAudio sample rate: {sr}"
                    if len(spl) > 2:
                        s += f"\nAudio channel: {spl[2]}"
                        if len(spl) > 4:
                            bps = spl[4].rstrip("b/s").casefold()
                            mult = 1
                            if bps.endswith("k"):
                                mult = 10 ** 3
                            elif bps.endswith("m"):
                                mult = 10 ** 6
                            elif bps.endswith("g"):
                                mult = 10 ** 9
                            bps = byte_scale(int(bps.split(None, 1)[0]) * mult, ratio=1000) + "bps"
                            s += f"\nAudio bitrate: {bps}"
                    out.append(code_md(s))
            elif mime[0] == "audio":
                search = "Duration:"
                resp = resp[resp.index(search) + len(search):]
                dur = time_disp(time_parse(resp[:resp.index(",")]), False)
                search = "Audio:"
                spl = regexp(r"\([^)]+\)").sub("", resp[resp.index(search) + len(search):].split("\n", 1)[0].strip()).strip().split(", ")
                s = f"Duration: {dur}\nFormat: {spl[0]}\nSample rate: {spl[1].split(None, 1)[0]}"
                if len(spl) > 2:
                    s += f"\nChannel: {spl[2]}"
                    if len(spl) > 4:
                        bps = spl[4].rstrip("b/s").casefold()
                        mult = 1
                        if bps.endswith("k"):
                            mult = 10 ** 3
                        elif bps.endswith("m"):
                            mult = 10 ** 6
                        elif bps.endswith("g"):
                            mult = 10 ** 9
                        bps = byte_scale(int(bps.split(None, 1)[0]) * mult, ratio=1000) + "bps"
                        s += f"\nBitrate: {bps}"
                out.append(code_md(s))
        return "".join(out)

    async def __call__(self, bot, channel, argv, user, message, **void):
        argv += " ".join(best_url(a) for a in message.attachments)
        urls = await bot.follow_url(argv, allow=True, images=False)
        if not urls:
            async for m2 in self.bot.history(message.channel, limit=5, before=message.id):
                argv = m2.content + " ".join(best_url(a) for a in m2.attachments)
                urls = await bot.follow_url(argv, allow=True, images=False)
                if urls:
                    break
        urls = set(urls)
        names = [url.rsplit("/", 1)[-1].rsplit("?", 1)[0] for url in urls]
        futs = [create_future(self.identify, url) for url in urls]
        fields = deque()
        for name, fut in zip(names, futs):
            resp = await fut
            fields.append((escape_markdown(name), resp))
        if not fields:
            raise FileNotFoundError("Please input a file by URL or attachment.")
        title = f"{len(fields)} file{'s' if len(fields) != 1 else ''} identified"
        await bot.send_as_embeds(channel, title=title, author=get_author(user), fields=sorted(fields))


class Follow(Command):
    name = ["🚶", "Follow_URL", "Redirect"]
    description = "Follows a discord message link and/or finds URLs in a string."
    usage = "<url>*"
    rate_limit = (1, 5)
    slash = True

    async def __call__(self, bot, channel, argv, message, **void):
        urls = find_urls(argv)
        if len(urls) == 1 and is_discord_message_link(urls[0]):
            spl = argv.rsplit("/", 2)
            channel = await bot.fetch_channel(spl[-2])
            msg = await bot.fetch_message(spl[-1], channel)
            argv = msg.content
            urls = find_urls(argv)
        out = set()
        for url in urls:
            if is_discord_message_link(url):
                temp = await self.bot.follow_url(url, allow=True)
            else:
                data = await self.bot.get_request(url)
                temp = find_urls(as_str(data))
            out.update(temp)
        if not out:
            raise FileNotFoundError("No valid URLs detected.")
        output = f"`Detected {len(out)} url{'s' if len(out) != 1 else ''}:`\n" + "\n".join(out)
        if len(output) > 2000 and len(output) < 54000:
            self.bot.send_as_embeds(channel, output, reference=message)
        else:
            return escape_roles(output)


class Match(Command):
    name = ["RE", "RegEx", "RexExp", "GREP"]
    description = "matches two strings using Linux-style RegExp, or computes the match ratio of two strings."
    usage = "<0:string1> <1:string2>?"
    rate_limit = (0.5, 2)
    no_parse = True

    async def __call__(self, args, name, **void):
        if len(args) < 2:
            raise ArgumentError("Please enter two or more strings to match.")
        if name == "match":
            regex = None
            for i in (1, -1):
                s = args[i]
                if len(s) >= 2 and s[0] == s[1] == "/":
                    if regex:
                        raise ArgumentError("Cannot match two Regular Expressions.")
                    regex = s[1:-1]
                    args.pop(i)
        else:
            regex = args.pop(0)
        if regex:
            temp = await create_future(re.findall, regex, " ".join(args))
            match = "\n".join(sqr_md(i) for i in temp)
        else:
            search = args.pop(0)
            s = " ".join(args)
            match = (
                sqr_md(round_min(round(fuzzy_substring(search, s) * 100, 6))) + "% literal match,\n"
                + sqr_md(round_min(round(fuzzy_substring(search.casefold(), s.casefold()) * 100, 6))) + "% case-insensitive match,\n"
                + sqr_md(round_min(round(fuzzy_substring(full_prune(search), full_prune(s)) * 100, 6))) + "% unicode mapping match."
            )
        return ini_md(match)


class Ask(Command):
    alias = ["How"]
    description = "Ask me any question, and I'll answer it!"
    usage = "<string>"
    # flags = "h"
    no_parse = True
    rate_limit = (0.5, 1)
    slash = True

    convos = {}

    async def __call__(self, message, channel, user, argv, name, flags=(), **void):
        bot = self.bot
        guild = getattr(channel, "guild", None)
        count = bot.data.users.get(user.id, {}).get("last_talk", 0)
        add_dict(bot.data.users, {user.id: {"last_talk": 1, "last_mention": 1}})
        bot.data.users[user.id]["last_used"] = utc()
        bot.data.users.update(user.id)
        await bot.seen(user, event="misc", raw="Talking to me")

        if "dailies" in bot.data:
            bot.data.dailies.progress_quests(user, "talk")
        if name == "how":
            if not argv.replace("?", ""):
                q = name
            else:
                q = (name + " " + argv).lstrip()
        elif len(argv) > 1:
            q = unicode_prune(argv)
        else:
            q = argv
        q = q.replace("？", "?")
        if not q.replace("?", ""):
            return "\xad" + choice(
                "Sorry, didn't see that, was that a question? 🤔",
                "Ay, speak up, I don't bite! :3",
                "Haha, nice try, I know that's not an actual question 🙃",
                "You thinking of asking an actual question?",
            )
        print(q)
        if q.casefold() in ("how", "how?"):
            await send_with_reply(channel, message, "https://imgur.com/gallery/8cfRt")
            return
        # if AUTH.get("huggingface_token"):
        try:
            cb = self.convos[channel.id]
        except KeyError:
            cb = self.convos[channel.id] = convobot.Bot(token=AUTH["huggingface_token"])
        with discord.context_managers.Typing(channel):
            out = await create_future(cb.talk, q)
        if out:
            await send_with_reply(channel, message, "\xad" + escape_roles(out))
            return
        q = single_space(q).strip().translate(bot.mtrans).replace("?", "\u200b").strip("\u200b")
        out = None
        q = grammarly_2_point_0(q)
        if q == "why":
            out = "Because! :3"
        elif q == "what":
            out = "Nothing! 🙃"
        elif q == "who":
            out = "Who, me?"
        elif q == "when":
            out = "Right now!"
        elif q == "where":
            out = "Here, dummy!"
        elif any(q.startswith(i) for i in ("what's ", "whats ", "what is ")) and regexp("[0-9]").search(q) and regexp("[+\\-*/\\\\^()").search(q):
            q = q[5:]
            q = q[q.index(" ") + 1:]
            try:
                if 0 <= q.rfind("<") < q.find(">"):
                    q = verify_id(q[q.rindex("<") + 1:q.index(">")])
                num = int(q)
            except ValueError:
                for _math in bot.commands.math:
                    answer = await _math(bot, q, "ask", channel, guild, {}, user)
                    if answer:
                        await send_with_reply(channel, "h" not in flags and message, answer)
                out = None
            else:
                if bot.in_cache(num) and "info" in bot.commands:
                    for _info in bot.commands.info:
                        await _info(num, None, "info", guild, channel, bot, user, "")
                    out = None
                else:
                    resp = await bot.solve_math(f"factorize {num}", timeout=20)
                    factors = safe_eval(resp[0])
                    out = f"{num}'s factors are `{', '.join(str(i) for i in factors)}`. If you'd like more information, try {bot.get_prefix(guild)}math!"
        elif q.startswith("who's ") or q.startswith("whos ") or q.startswith("who is "):
            q = q[4:].split(None, 1)[-1]
            member = await bot.fetch_member_ex(q, guild, allow_banned=False, fuzzy=None)
            if member:
                if "info" in bot.commands:
                    for _info in bot.commands.info:
                        await _info(q, None, "info", guild, channel, bot, user, "")
                    out = None
            else:
                members = guild.members
                members.remove(bot.user)
                members.remove(user)
                target = choice(choice(members).name, choice(members).display_name)
                out = alist(
                    f"Maybe it's your {random.choice(['therapist', 'doctor', 'parent', 'sibling', 'friend'])}!",
                    f"Hm, perhaps {target}!",
                    f"I am certain it's {target}!",
                    f"I think {target} might know... 👀",
                    "Me. 😏",
                )
                out = out[ihash(q) % len(out)]
        elif random.random() < 0.0625 + math.atan(count / 7) / 4:
            if xrand(3):
                if guild:
                    bots = [member for member in guild.members if member.bot and member.id != bot.id]
                answers = (
                    "Don't you have any work you should be doing?",
                    "Error: System backend refused connection. Please try again later.",
                    "That's interesting, gimme a minute to think about it.",
                    "Ay, I'm busy, ask me later!",
                    "¯\_(ツ)_/¯",
                    "Hm, I dunno, have you tried asking Google?",
                    "Apologies, didn't quite catch that, could you repeat?",
                    "Ay, ask me later, I'm busy with my 10 hour tunez! 🎧",
                    "Eh?",
                    f"My AI is ever growing, I think you should run. {get_random_emoji()}",
                    "Be sure to check out ~topic if you're ever in need of questions to answer! Oh, what was that again?",
                )
                if bots:
                    answers += (f"🥱 I'm tired... go ask {user_mention(choice(bots).id)}...",)
                resp = choice(answers)
            else:
                response = (
                    "I think it's time for me to ask a question of my own!",
                    "While I think about my answer, here's a question for you:",
                    "How about a question for you?",
                )
                resp = choice(response) + " " + choice(bot.data.users.questions)
            await send_with_reply(channel, message, resp)
            out = None
        elif any(q.startswith(i) for i in ("why ", "are ", "was ", "you ", "you're ")):
            out = alist(
                "Wouldn't know, might Google help?",
                f"Just to tease you, I refuse to answer. {get_random_emoji()}",
                f"Ask a {choice('therapist', 'doctor', 'parent', 'sibling', 'friend')}!",
                "Why not?",
                "It's obvious, isn't it? 😏",
                "Meh, does it matter?",
                "Why do you think?",
                "Who knows?",
            )
            out = out[ihash(q) % len(out)]
        elif q.startswith("when "):
            dt = utc_dt()
            year = dt.year
            out = alist(
                f"In the year {random.randint(year, year + 10000)}!",
                f"In {sec2time(xrand(601) * 60)}!",
                f"I'm only a bot, {user_mention(choice(bot.owners))} hasn't figured out time travel code yet!",
                f"Maybe go {choice('browse some social media', 'watch some YouTube')} and see if it's happened afterwards!",
                "Tomorrow?",
                "In a million years...",
                "Do you want it to happen now? Go out there and do it!",
                "Didn't that happen yesterday?",
                "Never. 😏",
                "How about an hour?",
                "Try it and find out!",
            )
            out = out[ihash(q) % len(out)]
        elif getattr((bot.commands.get(q.split(None, 1)[0]) or (None,))[0], "__name__", None) == "Hello":
            for _hello in bot.commands.hello:
                out = await _hello(bot, user, q.split(None, 1)[0], "".join(q.split(None, 1)[1:]), guild)
                if out:
                    await send_with_reply(channel, message, escape_roles(out))
                    return
        else:
            out = alist(
                "Yeah!",
                "Heck yeah!",
                "Uuuhhhmmm... Yes...?",
                "Mhm! 😊",
                "I believe so?",
                "What? No!",
                "Yeah!",
                "Yes :3",
                "Totally!",
                "Maybe?",
                "Definitely!",
                "Of course!",
                "I think so!",
                "I suppose so?",
                "Perhaps?",
                "Maybe not...",
                "Probably not?",
                "I guess not",
                "Nah 🙃",
                "Does it really matter?",
                "I dunno. ¯\_(ツ)_/¯",
                "Don't think so...",
            )
            out = out[ihash(q) % len(out)]
        if out:
            q = q[0].upper() + q[1:]
            await send_with_reply(channel, message, escape_roles(f"\xad{q}? {out}"))


class Random(Command):
    name = ["choice", "choose"]
    description = "Randomizes a set of arguments."
    usage = "<string>+"
    slash = True

    def __call__(self, argv, args, **void):
        if not args:
            raise ArgumentError("Input string is empty.")
        random.seed(time.time_ns())
        if "\n" in argv:
            x = choice(argv.splitlines())
        else:
            x = choice(args)
        return f"\xadI choose `{x}`!"


class Rate(Command):
    name = ["Rating", "Rank", "Ranking"]
    description = "Rates a given object with a random value out of 10!"
    usage = "<string>"
    slash = True

    async def __call__(self, bot, guild, argv, **void):
        rate = random.randint(0, 10)
        pronoun = "that"
        lego = f"`{grammarly_2_point_1(argv)}`"
        try:
            user = await bot.fetch_member_ex(verify_id(argv), guild, allow_banned=False, fuzzy=None)
        except:
            if re.match("<a?:[A-Za-z0-9\\-~_]+:[0-9]+>", argv):
                lego = argv
                pronoun = "it"
        else:
            lego = f"`{user.display_name}`"
            rate = 10
            pronoun = "them"
        lego = lego.replace("?", "").replace("!", "")
        return f"{lego}? I rate {pronoun} a `{rate}/10`!"

    
class WordCount(Command):
    name = ["Lc", "Wc", "Cc", "Character_Count", "Line_Count"]
    description = "Simple command that returns the word and character count of a supplied message. message.txt files work too!"
    usage = "<string>"
    slash = True

    async def __call__(self, argv, **void):
        if not argv:
            raise ArgumentError("Input string is empty.")
        if is_url(argv):
            argv = await self.bot.follow_url(argv, images=False)
        lc = argv.count("\n") + 1
        wc = len(argv.split())
        cc = len(argv)
        return f"Line count: `{lc}`\nWord count: `{wc}`\nCharacter count: `{cc}`"


class Topic(Command):
    name = ["Question"]
    description = "Asks a random question."
    usage = "<relationship{?r}>? <pickup-line{?p}>? <nsfw-pickup-line{?n}>?"
    flags = "npr"
    
    def __call__(self, bot, user, flags, channel, **void):
        create_task(bot.seen(user, event="misc", raw="Talking to me"))
        if "r" in flags:
            return "\u200b" + choice(bot.data.users.rquestions)
        elif "p" in flags:
            return "\u200b" + choice(bot.data.users.pickup_lines)
        elif "n" in flags:
            if is_nsfw(channel):
                return "\u200b" + choice(bot.data.users.nsfw_pickup_lines)
            raise PermissionError(f"This tag is only available in {uni_str('NSFW')} channels.")
        return "\u200b" + choice(bot.data.users.questions)


class Fact(Command):
    name = ["DailyFact", "UselessFact"]
    description = "Provides a random fact."

    async def __call__(self, bot, user, **void):
        create_task(bot.seen(user, event="misc", raw="Talking to me"))
        fact = await bot.data.flavour.get(p=False, q=False)
        return "\u200b" + fact


class Urban(Command):
    time_consuming = True
    name = ["📖", "UrbanDictionary"]
    description = "Searches Urban Dictionary for an item."
    usage = "<string>"
    flags = "v"
    rate_limit = (2, 8)
    typing = True
    slash = True
    header = {
        "accept-encoding": "application/gzip",
        "x-rapidapi-host": "mashape-community-urban-dictionary.p.rapidapi.com",
        "x-rapidapi-key": rapidapi_key,
    }

    async def __call__(self, channel, user, argv, message, **void):
        url = f"https://mashape-community-urban-dictionary.p.rapidapi.com/define?term={url_parse(argv)}"
        d = await Request(url, headers=self.header, timeout=12, json=True, aio=True)
        resp = d["list"]
        if not resp:
            raise LookupError(f"No results for {argv}.")
        resp.sort(
            key=lambda e: scale_ratio(e.get("thumbs_up", 0), e.get("thumbs_down", 0)),
            reverse=True,
        )
        title = argv
        fields = deque()
        for e in resp:
            fields.append(dict(
                name=e.get("word", argv),
                value=ini_md(e.get("definition", "")),
                inline=False,
            ))
        self.bot.send_as_embeds(channel, title=title, fields=fields, author=get_author(user), reference=message)
