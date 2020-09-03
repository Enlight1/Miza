# Smudge invaded, on the 1st August 2020 this become my territory *places flag* B3

#!/usr/bin/python3

from common import *

# Allows importing from commands and misc directories.
sys.path.insert(1, "commands")
sys.path.insert(1, "misc")


# Main class containing all global bot data.
class Bot(discord.AutoShardedClient, contextlib.AbstractContextManager, collections.abc.Callable):

    website = "https://github.com/thomas-xin/Miza"
    discord_icon = "https://cdn.discordapp.com/embed/avatars/0.png"
    heartbeat = "heartbeat.tmp"
    restart = "restart.tmp"
    shutdown = "shutdown.tmp"
    authdata = "auth.json"
    caches = ("guilds", "channels", "users", "roles", "emojis", "messages", "members", "deleted", "banned")
    statuses = (discord.Status.online, discord.Status.idle, discord.Status.dnd)
    # Default command prefix
    prefix = "~"
    # This is a fixed ID apparently
    deleted_user = 456226577798135808
    _globals = globals()
            
    def __init__(self, cache_size=4194304, timeout=24):
        # Initializes client (first in __mro__ of class inheritance)
        super().__init__(max_messages=256, heartbeat_timeout=timeout)
        self.cache_size = cache_size
        self.timeout = timeout
        self.set_classes()
        self.set_client_events()
        self.bot = self
        self.client = super()
        self.closed = False
        self.loaded = False
        # Base cache: contains all other caches
        self.cache = fcdict({c: {} for c in self.caches})
        # Channel-Webhook cache: for accessing all webhooks for a channel.
        self.cw_cache = cdict()
        self.events = mdict()
        self.react_sem = cdict()
        self.mention = ()
        self.semaphore = Semaphore(2, 1, delay=0.5)
        self.ready_semaphore = Semaphore(1, inf, delay=0.5)
        self.guild_semaphore = Semaphore(5, inf, delay=1, rate_limit=5)
        print("Time:", datetime.datetime.now())
        print("Initializing...")
        # O(1) time complexity for searching directory
        directory = frozenset(os.listdir())
        [os.mkdir(folder) for folder in ("cache", "saves", "deleted") if folder not in directory]
        try:
            f = open(self.authdata)
        except FileNotFoundError:
            with open(self.authdata, "w") as f:
                f.write(
                    '{\n'
                    + '"discord_token":"",\n'
                    + '"owner_id":""\n'
                    + '}'
                )
            print(f"ERROR: Please fill in details for {self.authdata} to continue.")
            self.setshutdown(2, force=True)
        with closing(f):
            auth = ast.literal_eval(f.read())
        try:
            self.token = auth["discord_token"]
        except KeyError:
            print("ERROR: discord_token not found. Unable to login.")
            self.setshutdown(force=True)
        try:
            owner_id = auth["owner_id"]
            if type(owner_id) not in (list, tuple):
                owner_id = {owner_id}
            self.owners = set(int(i) for i in owner_id)
        except KeyError:
            self.owners = set()
            print("WARNING: owner_id not found. Unable to locate owner.")
        # Initialize rest of bot variables
        self.proc = PROC
        self.guild_count = 0
        self.blocked = 0
        self.updated = False
        self.started = False
        self.ready = False
        self.stat_timer = 0
        self.last_check = 0
        self.status_iter = xrand(3)
        self.curr_state = azero(3)
        self.embed_senders = cdict()
        # Assign bot cache to global variables for convenience
        globals().update(self.cache)
        self.get_modules()

    __str__ = lambda self: str(self.user)
    __repr__ = lambda self: repr(self.user)

    __call__ = lambda self: self
    __exit__ = lambda self, *args, **kwargs: self.close()

    def __getattr__(self, key):
        with suppress(AttributeError):
            return object.__getattribute__(self, key)
        this = self._connection
        with suppress(AttributeError):
            return getattr(this, key)
        this = self.user
        with suppress(AttributeError):
            return getattr(this, key)
        this = self.__getattribute__("proc")
        return getattr(this, key)

    def __dir__(self):
        data = set(object.__dir__(self))
        data.update(dir(self._connection))
        data.update(dir(self.user))
        data.update(dir(self.proc))
        return data

    # Waits an amount of seconds and shuts down.
    def setshutdown(self, delay=None, force=False):
        if delay:
            time.sleep(delay)
        if force:
            touch(self.shutdown)
        force_kill(self.proc)

    # Starts up client.
    def run(self):
        print(f"Logging in...")
        with closing(get_event_loop()):
            with suppress():
                get_event_loop().run_until_complete(self.start(self.token))
            with suppress():
                get_event_loop().run_until_complete(self.close())
        self.setshutdown()

    # A reimplementation of the print builtin function.
    def print(self, *args, sep=" ", end="\n"):
        sys.__stdout__.write(str(sep).join(str(i) for i in args) + end)

    # Closes the bot, preventing all events.
    close = lambda self: setattr(self, "closed", True) or create_task(super().close())

    # A garbage collector for empty and unassigned objects in the database.
    async def garbage_collect(self, obj):
        if not self.ready or hasattr(obj, "no_delete"):
            return
        if obj.checking > utc():
            return
        obj.checking = utc() + 30
        data = obj.data
        for key in tuple(data):
            if key != 0 and type(key) is not str:
                with suppress():
                    # Database keys may be user, guild, or channel IDs
                    if getattr(obj, "user", None):
                        d = await self.fetch_user(key)
                    else:
                        if not data[key] and not started:
                            raise LookupError
                        with suppress():
                            d = await self.fetch_guild(key)
                            if d is not None:
                                continue
                        d = await self.fetch_channel(key)
                    if d is not None:
                        continue
                print(f"Deleting {key} from {repr(obj)}...")
                data.pop(key, None)
                obj.update()
            if random.random() > .99:
                await asyncio.sleep(0.2)
        obj.checking = utc() + 10

    # Calls a bot event, triggered by client events or others, across all bot databases. Calls may be sync or async.
    async def send_event(self, ev, *args, exc=False, **kwargs):
        if self.closed:
            return
        ctx = emptyctx if exc else tracebacksuppressor
        events = self.events.get(ev, ())
        if len(events) == 1:
            with ctx:
                return await create_future(events[0](*args, **kwargs))
            return
        futs = [create_future(func(*args, **kwargs)) for func in events]
        out = deque()
        for fut in futs:
            with ctx:
                res = await fut
                out.append(res)
        return out

    # Gets the first accessable text channel in the target guild.
    async def get_first_sendable(self, guild, member):
        if member is None:
            return guild.owner
        channel = guild.system_channel
        if channel is None or not channel.permissions_for(member).send_messages:
            channel = guild.rules_channel
            if channel is None or not channel.permissions_for(member).send_messages:
                found = False
                if guild.text_channels:
                    for channel in guild.text_channels:
                        if channel.permissions_for(member).send_messages:
                            found = True
                            break
                if not found:
                    return guild.owner
        return channel

    # Returns a discord object if it is in any of the internal cache.
    def in_cache(self, o_id):
        cache = self.cache
        with suppress(KeyError):
            return self.cache.users[o_id]
        with suppress(KeyError):
            return self.cache.channels[o_id]
        with suppress(KeyError):
            return self.cache.guilds[o_id]
        with suppress(KeyError):
            return self.cache.roles[o_id]
        with suppress(KeyError):
            return self.cache.emojis[o_id]
        with suppress(KeyError):
            return self.data.mimics[o_id]

    # Fetches either a user or channel object from ID, using the bot cache when possible.
    async def fetch_messageable(self, s_id):
        if type(s_id) is not int:
            try:
                s_id = int(s_id)
            except (ValueError, TypeError):
                raise TypeError(f"Invalid messageable identifier: {s_id}")
        with suppress(KeyError):
            return self.get_user(s_id)
        with suppress(KeyError):
            return self.cache.channels[s_id]
        try:
            user = await super().fetch_user(s_id)
        except LookupError:
            channel = await super().fetch_channel(s_id)
            self.cache.channels[s_id] = channel
            self.limit_cache("channels")
            return channel
        self.cache.users[u_id] = user
        self.limit_cache("users")
        return user

    # Fetches a user from ID, using the bot cache when possible.
    async def fetch_user(self, u_id):
        with suppress(KeyError):
            return self.get_user(u_id)
        u_id = verify_id(u_id)
        if type(u_id) is not int:
            raise TypeError(f"Invalid user identifier: {u_id}")
        user = await super().fetch_user(u_id)
        self.cache.users[u_id] = user
        self.limit_cache("users")
        return user

    # Gets a user from ID, using the bot cache.
    def get_user(self, u_id, replace=False):
        if type(u_id) is not int:
            try:
                u_id = int(u_id)
            except (ValueError, TypeError):
                raise TypeError(f"Invalid user identifier: {u_id}")
        with suppress(KeyError):
            return self.cache.users[u_id]
        if u_id == self.deleted_user:
            user = self.GhostUser()
            user.system = True
            user.name = "Deleted User"
            user.display_name = "Deleted User"
            user.id = u_id
            user.avatar_url = self.discord_icon
        else:
            try:
                user = super().get_user(u_id)
                if user is None:
                    raise LookupError
            except:
                if replace:
                    return self.get_user(self.deleted_user)
                raise KeyError("Target user ID not found.")
        self.cache.users[u_id] = user
        self.limit_cache("users")
        return user

    async def find_users(self, argl, args, user, guild):
        if not argl and not args:
            return (user,)
        if argl:
            users = {}
            for u_id in argl:
                u = await self.fetch_user_member(u_id, guild)
                users[u.id] = u
            return users.values()
        u_id = verify_id(args.pop(0))
        if type(u_id) is int:
            role = guild.get_role(u_id)
            if role is not None:
                return role.members
        elif "@" in u_id and ("everyone" in u_id or "here" in u_id):
            return await self.get_full_members(guild)
        u = await self.fetch_user_member(u_id, guild)
        return (u,)

    async def fetch_user_member(self, u_id, guild=None):
        u_id = verify_id(u_id)
        if type(u_id) is int:
            try:
                user = self.cache.users[u_id]
            except KeyError:
                user = await self.fetch_user(u_id)
            with suppress():
                if guild:
                    temp = guild.get_member(user.id)
                    if temp is not None:
                        return temp
            with suppress():
                return self.get_member(u_id, guild)
            return user
        return await self.fetch_member_ex(u_id, guild)

    async def get_full_members(self, guild):
        members = guild._members.values()
        if "bans" in self.data:
            members = set(members)
            for b in self.data.bans.get(guild.id, ()):
                try:
                    user = await self.fetch_user(b.get("u", self.deleted_user))
                except LookupError:
                    user = self.cache.users[self.deleted_user]
                members.add(user)
        return members

    async def query_members(self, members, query):
        if type(query) is not str:
            query = str(query)
        with suppress(LookupError):
            return await str_lookup(
                members,
                query,
                qkey=userQuery1,
                ikey=userIter1,
                loose=False,
            )
        with suppress(LookupError):
            return await str_lookup(
                members,
                query,
                qkey=userQuery2,
                ikey=userIter2,
            )
        with suppress(LookupError):
            return await str_lookup(
                members,
                query,
                qkey=userQuery3,
                ikey=userIter3,
            )
        with suppress(LookupError):
            return await str_lookup(
                members,
                query,
                qkey=userQuery4,
                ikey=userIter4,
                fuzzy=1 / 3,
            )
        try:
            members = await guild.query_members(query, limit=1)
            return members[0]
        except (AttributeError, T0, T1):
            raise LookupError(f"No results for {query}.")

    # Fetches a member in the target server by ID or name lookup.
    async def fetch_member_ex(self, u_id, guild=None, allow_banned=True):
        if type(u_id) is not int:
            with suppress(TypeError, ValueError):
                u_id = int(u_id)
        member = None
        if type(u_id) is int:
            member = guild.get_member(u_id)
        if member is None:
            if type(u_id) is int:
                with suppress(LookupError):
                    member = await self.fetch_member(u_id, guild)
            if member is None:
                if allow_banned:
                    members = await self.get_full_members(guild)
                else:
                    members = guild.members
                if not members:
                    members = guild.members = await guild.fetch_members(limit=None)
                    guild._members.update({m.id: m for m in members})
                return await self.query_members(members, u_id)
        return member

    # Fetches the first seen instance of the target user as a member in any shared server.
    async def fetch_member(self, u_id, guild=None, find_others=False):
        if type(u_id) is not int:
            try:
                u_id = int(u_id)
            except (ValueError, TypeError):
                raise TypeError(f"Invalid user identifier: {u_id}")
        if find_others:
            with suppress(LookupError):
                member = self.cache.members[u_id].guild.get_member(u_id)
                if member is None:
                    raise LookupError
                return member
        g = bot.cache.guilds
        if guild is None:
            guilds = deque(bot.cache.guilds.values())
        else:
            if find_others:
                guilds = deque(g[i] for i in g if g[i].id != guild.id)
                guilds.appendleft(guild)
            else:
                guilds = [guild]
        member = None
        for i, guild in enumerate(guilds, 1):
            member = guild.get_member(u_id)
            if member is not None:
                break
            if not i & 4095:
                await asyncio.sleep(0.2)
        if member is None:
            raise LookupError("Unable to find member data.")
        self.cache.members[u_id] = member
        self.limit_cache("members")
        return member

    def get_member(self, u_id, guild=None):
        if type(u_id) is not int:
            try:
                u_id = int(u_id)
            except (ValueError, TypeError):
                raise TypeError(f"Invalid user identifier: {u_id}")
        with suppress(LookupError):
            member = self.cache.members[u_id].guild.get_member(u_id)
            if member is None:
                raise LookupError
            return member
        g = bot.cache.guilds
        if guild is None:
            guilds = deque(bot.cache.guilds.values())
        else:
            guilds = deque(g[i] for i in g if g[i].id != guild.id)
            guilds.appendleft(guild)
        member = None
        for guild in guilds:
            member = guild.get_member(u_id)
            if member is not None:
                break
        if member is None:
            raise LookupError("Unable to find member data.")
        self.cache.members[u_id] = member
        self.limit_cache("members")
        return member

    # Fetches a guild from ID, using the bot cache when possible.
    async def fetch_guild(self, g_id, follow_invites=True):
        if type(g_id) is not int:
            try:
                g_id = int(g_id)
            except (ValueError, TypeError):
                if follow_invites:
                    try:
                        # Parse and follow invites to get partial guild info
                        invite = await super().fetch_invite(g_id.strip("< >"))
                        g = invite.guild
                        if not hasattr(g, "member_count"):
                            guild = cdict(member_count=invite.approximate_member_count)
                            for at in g.__slots__:
                                setattr(guild, at, getattr(g, at))
                            icon = str(guild.icon)
                            guild.icon_url = f"https://cdn.discordapp.com/icons/{guild.id}/{icon}"
                            if icon.startswith("a_"):
                                guild.icon_url += ".gif"
                        else:
                            guild = g
                        return guild
                    except (discord.NotFound, discord.HTTPException) as ex:
                        raise LookupError(str(ex))
                raise TypeError(f"Invalid server identifier: {g_id}")
        with suppress(KeyError):
            return self.cache.guilds[g_id]
        try:
            guild = super().get_guild(g_id)
            if guild is None:
                raise EOFError
        except:
            guild = await super().fetch_guild(g_id)
        self.cache.guilds[g_id] = guild
        self.limit_cache("guilds")
        return guild

    # Fetches a channel from ID, using the bot cache when possible.
    async def fetch_channel(self, c_id):
        if type(c_id) is not int:
            try:
                c_id = int(c_id)
            except (ValueError, TypeError):
                raise TypeError(f"Invalid channel identifier: {c_id}")
        with suppress(KeyError):
            return self.cache.channels[c_id]
        channel = await super().fetch_channel(c_id)
        self.cache.channels[c_id] = channel
        self.limit_cache("channels")
        return channel

    # Fetches a message from ID and channel, using the bot cache when possible.
    async def fetch_message(self, m_id, channel=None):
        if type(m_id) is not int:
            try:
                m_id = int(m_id)
            except (ValueError, TypeError):
                raise TypeError(f"Invalid message identifier: {m_id}")
        with suppress(KeyError):
            return self.cache.messages[m_id]
        if channel is None:
            raise LookupError("Message data not found.")
        with suppress(TypeError):
            int(channel)
            channel = await self.fetch_channel(channel)
        message = await channel.fetch_message(m_id)
        if message is not None:
            self.add_message(message)
        return message

    # Fetches a role from ID and guild, using the bot cache when possible.
    async def fetch_role(self, r_id, guild):
        if type(r_id) is not int:
            try:
                r_id = int(r_id)
            except (ValueError, TypeError):
                raise TypeError("Invalid role identifier: " + str(r_id))
        with suppress(KeyError):
            return self.cache.roles[r_id]
        try:
            role = guild.get_role(r_id)
            if role is None:
                raise EOFError
        except:
            if len(guild.roles) <= 1:
                roles = await guild.fetch_roles()
                guild.roles = sorted(roles)
                role = discord.utils.get(roles, id=r_id)
            if role is None:
                raise LookupError("Role not found.")
        self.cache.roles[r_id] = role
        self.limit_cache("roles")
        return role

    # Fetches an emoji from ID and guild, using the bot cache when possible.
    async def fetch_emoji(self, e_id, guild=None):
        if type(e_id) is not int:
            try:
                e_id = int(e_id)
            except (ValueError, TypeError):
                raise TypeError("Invalid emoji identifier: " + str(e_id))
        with suppress(KeyError):
            return self.cache.emojis[e_id]
        try:
            emoji = super().get_emoji(e_id)
            if emoji is None:
                raise EOFError
        except:
            if guild is not None:
                emoji = await guild.fetch_emoji(e_id)
            else:
                raise discord.NotFound("Emoji not found.")
        self.cache.emojis[e_id] = emoji
        self.limit_cache("emojis")
        return emoji
    
    # Searches the bot database for a webhook mimic from ID.
    def get_mimic(self, m_id, user=None):
        if "mimics" in self.data:
            with suppress(KeyError):
                with suppress(ValueError, TypeError):
                    m_id = "&" + str(int(m_id))
                mimic = self.data.mimics[m_id]
                return mimic
            if user is not None:
                with suppress(KeyError):
                    mimics = self.data.mimics[user.id]
                    mlist = mimics[m_id]
                    return self.get_mimic(choice(mlist))
        raise LookupError("Unable to find target mimic.")

    # Gets the DM channel for the target user, creating a new one if none exists.
    async def get_dm(self, user):
        with suppress(TypeError):
            int(user)
            user = await self.fetch_user(user)
        channel = user.dm_channel
        if channel is None:
            channel = await user.create_dm()
        return channel

    # Finds URLs in a string, following any discord message links found.
    async def follow_url(self, url, it=None, best=False, preserve=True, images=True, allow=False, limit=None):
        if limit is not None and limit <= 0:
            return []
        if it is None:
            urls = find_urls(url)
            if not urls:
                return []
            it = {}
        else:
            urls = [url]
        out = deque()
        if preserve or allow:
            lost = deque()
        else:
            lost = None
        if images:
            medias = ("video", "image", "thumbnail")
        else:
            medias = "video"
        for url in urls:
            if is_discord_message_link(url):
                found = deque()
                spl = url[url.index("channels/") + 9:].replace("?", "/").split("/")
                c = await self.fetch_channel(spl[1])
                m = await self.fetch_message(spl[2], c)
                # All attachments should be valid URLs
                if best:
                    found.extend(best_url(a) for a in m.attachments)
                else:
                    found.extend(a.url for a in m.attachments)
                found.extend(find_urls(m.content))
                # Attempt to find URLs in embed contents
                for e in m.embeds:
                    for a in medias:
                        obj = getattr(e, a, None)
                        if obj:
                            if best:
                                url = best_url(obj)
                            else:
                                url = obj.url
                            if url:
                                found.append(url)
                                break
                # Attempt to find URLs in embed descriptions
                [found.extend(find_urls(e.description)) for e in m.embeds if e.description]
                for u in found:
                    # Do not attempt to find the same URL twice
                    if u not in it:
                        it[u] = True
                        if not len(it) & 255:
                            await asyncio.sleep(0.2)
                        found2 = await self.follow_url(u, it, best=best, preserve=preserve, images=images, allow=allow, limit=limit)
                        if len(found2):
                            out.extend(found2)
                        elif allow and m.content:
                            lost.append(m.content)
                        elif preserve:
                            lost.append(u)
            elif images and is_imgur_url(url):
                first = url.split("?")[0]
                if not first.endswith(".jpg"):
                    first += ".jpg"
                out.append(first)
            elif images and is_giphy_url(url):
                first = url.split("?")[0]
                item = first[first.rindex("/") + 1:]
                out.append(f"https://media2.giphy.com/media/{item}/giphy.gif")
            elif images and is_tenor_url(url):
                s = await Request(url, decode=True, aio=True)
                search ='<meta class="dynamic" property="og:image" content="'
                s = s[s.index(search) + len(search):]
                s = s[:s.index('"')]
                out.append(s)
            else:
                out.append(url)
        if lost:
            out.extend(lost)
        if not out:
            return urls
        if limit is not None:
            return list(out)[:limit]
        return out

    # Follows a message link, replacing emojis and user mentions with their icon URLs.
    async def follow_to_image(self, url):
        temp = find_urls(url)
        if temp:
            return temp
        users = find_users(url)
        emojis = find_emojis(url)
        out = deque()
        if users:
            futs = [create_task(self.fetch_user(verify_id(u))) for u in users]
            for fut in futs:
                with suppress(LookupError):
                    res = await fut
                    out.append(best_url(res))
        for s in emojis:
            s = s[3:]
            i = s.index(":")
            e_id = s[i + 1:s.rindex(">")]
            try:
                out.append(self.emojis[e_id].url)
            except KeyError:
                url = f"https://cdn.discordapp.com/emojis/{e_id}.gif"
                with requests.get(url, stream=True) as resp:
                    if resp.status_code >= 400:
                        url = url[:-3] + "png"
            out.append(url)
        return out

    # Inserts a message into the bot cache, discarding existing ones if full.
    def add_message(self, message):
        self.cache.messages[message.id] = message
        self.limit_cache("messages")
        return message

    # Deletes a message from the bot cache.
    def remove_message(self, message):
        self.cache.messages.pop(message.id, None)
        if not message.author.bot:
            s = message_repr(message, username=True)
            ch = f"deleted/{message.channel.id}.txt"
            print(s, file=ch)

    # Limits a cache to a certain amount, discarding oldest entries first.
    def limit_cache(self, cache=None, limit=None):
        if limit is None:
            limit = self.cache_size
        if cache is not None:
            caches = [self.cache[cache]]
        else:
            caches = self.cache.values()
        for c in caches:
            while len(c) > limit:
                c.pop(next(iter(c)))
    
    # Updates bot cache from the discord.py client cache.
    def update_from_client(self):
        self.cache.guilds.update(self._guilds)
        self.cache.emojis.update(self._emojis)
        self.cache.users.update(self._users)
        self.cache.channels.update(self._private_channels)

    # Updates bot cache from the discord.py guild objects.
    def update_from_guilds(self):
        for i, guild in enumerate(self.guilds, 1):
            self.cache.channels.update(guild._channels)
            self.cache.roles.update(guild._roles)
            if not i & 63:
                time.sleep(0.2)

    # Gets the target bot prefix for the target guild, return the default one if none exists.
    def get_prefix(self, guild):
        try:
            g_id = guild.id
        except AttributeError:
            try:
                g_id = int(guild)
            except TypeError:
                g_id = 0
        with suppress(KeyError):
            return self.data.prefixes[g_id]
        return self.prefix

    # Gets effective permission level for the target user in a certain guild, taking into account roles.
    def get_perms(self, user, guild=None):
        try:
            u_id = user.id
        except AttributeError:
            u_id = int(user)
        if self.is_owner(u_id):
            return nan
        if self.is_blacklisted(u_id):
            return -inf
        if u_id == self.id:
            return inf
        if guild is None or hasattr(guild, "ghost"):
            return inf
        if u_id == guild.owner_id:
            return inf
        with suppress(KeyError):
            perm = self.data.perms[guild.id][u_id]
            if isnan(perm):
                return -inf
            return perm
        m = guild.get_member(u_id)
        if m is None:
            r = guild.get_role(u_id)
            if r is None:
                with suppress(KeyError):
                    return self.data.perms[guild.id][guild.id]
                return -inf
            return self.get_role_perms(r, guild)
        p = m.guild_permissions
        if p.administrator:
            return inf
        perm = -inf
        for role in m.roles:
            rp = self.get_role_perms(role, guild)
            if rp > perm:
                perm = rp
        if isnan(perm):
            perm = -inf
        return perm
    
    # Gets effective permission level for the target role in a certain guild, taking into account permission values.
    def get_role_perms(self, role, guild):
        if role.permissions.administrator:
            return inf
        with suppress(KeyError):
            perm = self.data.perms[guild.id][role.id]
            if isnan(perm):
                return -inf
            return perm
        if guild.id == role.id:
            return 0
        p = role.permissions
        if all((p.ban_members, p.manage_channels, p.manage_guild, p.manage_roles, p.manage_messages)):
            return 4
        elif any((p.ban_members, p.manage_channels, p.manage_guild)):
            return 3
        elif any((p.kick_members, p.manage_messages, p.manage_nicknames, p.manage_roles, p.manage_webhooks, p.manage_emojis)):
            return 2
        elif any((p.view_audit_log, p.priority_speaker, p.mention_everyone, p.move_members)):
            return 1
        return -1

    # Sets the permission value for a snowflake in a guild to a value.
    def set_perms(self, user, guild, value):
        perms = self.data.perms
        try:
            u_id = user.id
        except AttributeError:
            u_id = user
        g_perm = set_dict(perms, guild.id, {})
        g_perm.update({u_id: round_min(value)})
        self.database.perms.update()

    # Checks whether a member's status was changed.
    def status_changed(self, before, after):
        if before.activity != after.activity:
            return True
        for attr in ("status", "desktop_status", "web_status", "mobile_status"):
            b, a = getattr(before, attr), getattr(after, attr)
            if b == a:
                return False
        return True
    
    # Checks whether a member's status was updated by themselves.
    def status_updated(self, before, after):
        if before.activity != after.activity:
            return True
        for attr in ("status", "desktop_status", "web_status", "mobile_status"):
            b, a = getattr(before, attr), getattr(after, attr)
            if b == discord.Status.online and a == discord.Status.idle:
                if utc() - self.data.users.get(after.id, {}).get("last_seen", 0) < 900:
                    return False
            elif a == discord.Status.offline:
                return False
            elif b == a:
                return False
        return True

    # Checks if a message has been flagged as deleted by the deleted cache.
    def is_deleted(self, message):
        try:
            m_id = int(message.id)
        except AttributeError:
            m_id = int(message)
        return self.cache.deleted.get(m_id, False)

    # Logs if a message has been deleted.
    def log_delete(self, message, no_log=False):
        try:
            m_id = int(message.id)
        except AttributeError:
            m_id = int(message)
        self.cache.deleted[m_id] = no_log + 2
        self.limit_cache("deleted", limit=4096)
    
    # Silently deletes a message, bypassing logs.
    async def silent_delete(self, message, exc=False, no_log=False, delay=None):
        if delay:
            await asyncio.sleep(float(delay))
        try:
            self.log_delete(message, no_log)
            await message.delete()
        except:
            self.cache.deleted.pop(message.id, None)
            if exc:
                raise
    
    async def verified_ban(self, user, guild, reason=None):
        self.cache.banned[(guild.id, user.id)] = utc()
        try:
            await guild.ban(user, delete_message_days=0, reason=reason)
        except:
            self.cache.banned.pop((guild.id, user.id), None)
            raise
        self.cache.banned[(guild.id, user.id)] = utc()
        self.limit_cache("banned", 4096)
    
    def recently_banned(self, user, guild, duration=20):
        return utc() - self.cache.banned.get((verify_id(guild), verify_id(user)), 0) < duration

    def is_mentioned(self, message, user, guild=None):
        u_id = verify_id(user)
        if u_id in (member.id for member in message.mentions):
            return True
        if guild is None:
            return False
        member = guild.get_member(u_id)
        if member is None:
            return False
        if message.content.count("`") > 1:
            return False
        for role in member.roles:
            if not role.mentionable:
                if role.mention in message.content:
                    return True
        return False

    # Checks if a user is an owner of the bot.
    is_owner = lambda self, user: verify_id(user) in self.owners

    # Checks if a guild is trusted by the bot.
    def is_trusted(self, guild):
        try:
            trusted = self.data.trusted
        except (AttributeError, KeyError):
            return False
        return verify_id(guild) in trusted

    # Checks if a user is blacklisted from the bot.
    def is_blacklisted(self, user):
        u_id = verify_id(user)
        if self.is_owner(u_id) or u_id == self.id:
            return False
        with suppress(KeyError):
            return u_id in self.data.blacklist
        return True

    dangerous_command = bold(css_md(uni_str('[WARNING: POTENTIALLY DANGEROUS COMMAND ENTERED. REPEAT COMMAND WITH "?f" FLAG TO CONFIRM.]')))
    
    mmap = {
        "“": '"',
        "”": '"',
        "„": '"',
        "‘": "'",
        "’": "'",
        "‚": "'",
        "〝": '"',
        "〞": '"',
        "⸌": "'",
        "⸍": "'",
        "⸢": "'",
        "⸣": "'",
        "⸤": "'",
        "⸥": "'",
        "⸨": "((",
        "⸩": "))",
        "⟦": "[",
        "⟧": "]",
        "〚": "[",
        "〛": "]",
        "「": "[",
        "」": "]",
        "『": "[",
        "』": "]",
        "【": "[",
        "】": "]",
        "〖": "[",
        "〗": "]",
        "（": "(",
        "）": ")",
        "［": "[",
        "］": "]",
        "｛": "{",
        "｝": "}",
        "⌈": "[",
        "⌉": "]",
        "⌊": "[",
        "⌋": "]",
        "⦋": "[",
        "⦌": "]",
        "⦍": "[",
        "⦐": "]",
        "⦏": "[",
        "⦎": "]",
        "⁅": "[",
        "⁆": "]",
        "〔": "[",
        "〕": "]",
        "«": "<<",
        "»": ">>",
        "❮": "<",
        "❯": ">",
        "❰": "<",
        "❱": ">",
        "❬": "<",
        "❭": ">",
        "＜": "<",
        "＞": ">",
        "⟨": "<",
        "⟩": ">",
    }
    mtrans = "".maketrans(mmap)

    cmap = {
        "<": "alist((",
        ">": "))",
    }
    ctrans = "".maketrans(cmap)

    op = {
        "=": None,
        ":=": None,
        "+=": "__add__",
        "-=": "__sub__",
        "*=": "__mul__",
        "/=": "__truediv__",
        "//=": "__floordiv__",
        "**=": "__pow__",
        "^=": "__pow__",
        "%=": "__mod__",
    }

    # Evaluates a math formula to a float value, using a math process from the subprocess pool when necessary.
    async def eval_math(self, expr, obj=None, default=0, op=True):
        if op:
            # Allow mathematical operations on a default value
            _op = None
            for op, at in self.op.items():
                if expr.startswith(op):
                    expr = expr[len(op):].strip()
                    _op = at
            num = await self.eval_math(expr, obj, op=False)
            if _op is not None:
                num = getattr(float(default), _op)(num)
            return num
        f = expr.strip()
        try:
            if not f:
                r = [0]
            else:
                s = f.casefold()
                if s in ("t", "true", "y", "yes", "on"):
                    r = [True]
                elif s in ("f", "false", "n", "no", "off"):
                    r = [False]
                elif s == "inf":
                    r = [inf]
                elif s == "-inf":
                    r = [-inf]
                elif s in ("nan", "-nan"):
                    r = [nan]
                else:
                    r = [ast.literal_eval(f)]
        except (ValueError, TypeError, SyntaxError):
            r = await self.solve_math(f, obj, 16, 0)
        x = r[0]
        with suppress(TypeError):
            while True:
                if type(x) is str:
                    raise TypeError
                x = tuple(x)[0]
        return round_min(float(x))

    # Evaluates a math formula to a list of answers, using a math process from the subprocess pool when necessary.
    async def solve_math(self, f, obj, prec, r, timeout=12):
        f = f.strip()
        try:
            if obj is None:
                key = None
            elif hasattr(obj, "ghost"):
                key = self.deleted_user
            else:
                key = obj.id
        except AttributeError:
            key = int(obj)
        # Bot owners have no semaphore limit
        if self.is_owner(key):
            key = None
        return await process_math(f, int(prec), int(r), key, timeout=12)

    TimeChecks = {
        "galactic year": ("gy", "galactic year", "galactic years"),
        "millenium": ("ml", "millenium", "millenia"),
        "century": ("c", "century", "centuries"),
        "decade": ("dc", "decade", "decades"),
        "year": ("y", "year", "years"),
        "month": ("mo", "mth", "month", "mos", "mths", "months"),
        "week": ("w", "wk", "week", "wks", "weeks"),
        "day": ("d", "day", "days"),
        "hour": ("h", "hr", "hour", "hrs", "hours"),
        "minute": ("m", "min", "minute", "mins", "minutes"),
        "second": ("s", "sec", "second", "secs", "seconds"),
    }
    num_words = "(?:(?:(?:[0-9]+|[a-z]{1,}illion)|thousand|hundred|ten|eleven|twelve|(?:thir|four|fif|six|seven|eigh|nine)teen|(?:twen|thir|for|fif|six|seven|eigh|nine)ty|zero|one|two|three|four|five|six|seven|eight|nine)\\s*)"
    numericals = re.compile("^(?:" + num_words + "|(?:a|an)\\s*)(?:" + num_words + ")*", re.I)
    connectors = re.compile("\\s(?:and|at)\\s", re.I)
    alphabet = frozenset("abcdefghijklmnopqrstuvwxyz")

    # Evaluates a time input, using a math process from the subprocess pool when necessary.
    async def eval_time(self, expr, obj=None, default=0, op=True):
        if op:
            # Allow mathematical operations on a default value
            _op = None
            for op, at in self.op.items():
                if expr.startswith(op):
                    expr = expr[len(op):].strip(" ")
                    _op = at
            num = await self.eval_time(expr, obj, op=False)
            if _op is not None:
                num = getattr(float(default), _op)(num)
            return num
        t = 0
        if expr:
            f = None
            if " " in expr:
                # Parse timezones first
                try:
                    args = shlex.split(expr)
                except ValueError:
                    args = expr.split()
                for a in (args[0], args[-1]):
                    tz = a.casefold()
                    if tz in TIMEZONES:
                        t = -get_timezone(tz)
                        expr = expr.replace(a, "")
                        break
            try:
                # Try to evaluate time inputs
                if ":" in expr:
                    data = expr.split(":")
                    mult = 1
                    while len(data):
                        t += await self.eval_math(data[-1], obj) * mult
                        data = data[:-1]
                        if mult <= 60:
                            mult *= 60
                        elif mult <= 3600:
                            mult *= 24
                        elif len(data):
                            raise TypeError("Too many time arguments.")
                else:
                    # Otherwise move on to main parser
                    f = single_space(re.sub(self.connectors, " ", expr.replace(",", " "))).casefold()
                    for tc in self.TimeChecks:
                        for check in reversed(self.TimeChecks[tc]):
                            if check in f:
                                i = f.index(check)
                                isnt = i + len(check) < len(f) and f[i + len(check)] in self.alphabet
                                if isnt or not i or f[i - 1] in self.alphabet:
                                    continue
                                temp = f[:i]
                                f = f[i + len(check):].strip()
                                match = re.search(self.numericals, temp)
                                if match:
                                    i = match.end()
                                    n = num_parse(temp[:i])
                                    temp = temp[i:].strip()
                                    if temp:
                                        f = temp + " " + f
                                else:
                                    n = await self.eval_math(temp, obj)
                                s = TIMEUNITS[tc]
                                if type(s) is list:
                                    s = s[0]
                                t += s * n
                    temp = f.strip()
                    if temp:
                        match = re.search(self.numericals, temp)
                        if match:
                            i = match.end()
                            n = num_parse(temp[:i])
                            temp = temp[i:].strip()
                            if temp:
                                n = await self.eval_math(str(n) + " " + temp, obj)
                        else:
                            n = await self.eval_math(temp, obj)
                        t += n
            except:
                # Use datetime parser if regular parser fails
                t = utc_ts(tzparse(f if f else expr)) - utc_ts(tparser.parse("0s"))
        if type(t) is not float:
            t = float(t)
        return t

    ip_check = re.compile("^([0-9]{1,3}\\.){3}[0-9]{1,3}$")

    # Updates the bot's stored external IP address.
    def update_ip(self, ip):
        if re.search(self.ip_check, ip):
            self.ip = ip

    # Gets the external IP address from api.ipify.org
    async def get_ip(self):
        resp = await Request("https://api.ipify.org", decode=True, aio=True)
        self.update_ip(resp)

    # Gets the amount of active processes, threads, coroutines.
    def get_active(self):
        procs = 2 + sum(1 for c in self.proc.children(True))
        thrds = self.proc.num_threads()
        coros = sum(1 for i in asyncio.all_tasks())
        return alist((procs, thrds, coros))

    # Gets the CPU and memory usage of a process over a period of 1 second.
    async def get_proc_state(self, proc):
        with suppress(psutil.NoSuchProcess):
            create_future_ex(proc.cpu_percent, priority=True)
            await asyncio.sleep(1)
            c = await create_future(proc.cpu_percent, priority=True)
            m = await create_future(proc.memory_percent, priority=True)
            return float(c), float(m)
        return 0, 0

    # Gets the total size of the cache folder.
    get_cache_size = lambda self: sum(os.path.getsize("cache/" + fn) for fn in os.listdir("cache"))

    # Gets the status of the bot.
    async def get_state(self):
        stats = azero(3)
        procs = await create_future(self.proc.children, recursive=True, priority=True)
        procs.append(self.proc)
        tasks = [self.get_proc_state(p) for p in procs]
        resp = await recursive_coro(tasks)
        stats += [sum(st[0] for st in resp), sum(st[1] for st in resp), 0]
        cpu = await create_future(psutil.cpu_count, priority=True)
        mem = await create_future(psutil.virtual_memory, priority=True)
        disk = await create_future(self.get_cache_size, priority=True)
        # CPU is totalled across all cores
        stats[0] /= cpu
        # Memory is in %
        stats[1] *= mem.total / 100
        stats[2] = disk
        self.size2 = fcdict()
        files = await create_future(os.listdir, "misc", priority=True)
        for f in files:
            path = "misc/" + f
            if is_code(path):
                self.size2[f] = line_count(path)
        self.curr_state = stats
        return stats

    # Loads a module containing commands and databases by name.
    def get_module(self, module):
        with tracebacksuppressor:
            f = module
            if "." in f:
                f = f[:f.rindex(".")]
            path, module = module, f
            new = False
            if module in self._globals:
                print(f"Reloading module {module}...")
                if module in self.categories:
                    self.unload(module)
                mod = importlib.reload(self._globals[module])
            else:
                print(f"Loading module {module}...")
                new = True
                mod = __import__(module)
            self._globals[module] = mod
            commands = alist()
            dataitems = alist()
            items = mod.__dict__
            for var in items.values():
                if callable(var) and var not in (Command, Database):
                    load_type = 0
                    with suppress(TypeError):
                        if issubclass(var, Command):
                            load_type = 1
                        elif issubclass(var, Database):
                            load_type = 2
                    if load_type:
                        obj = var(self, module)
                        if load_type == 1:
                            commands.append(obj)
                            print(f"Successfully loaded command {repr(obj)}.")
                        elif load_type == 2:
                            dataitems.append(obj)
                            print(f"Successfully loaded database {repr(obj)}.")
            for u in dataitems:
                for c in commands:
                    c.data[u.name] = u
            self.categories[module] = commands
            self.dbitems[module] = dataitems
            self.size[module] = line_count("commands/" + path)
            if not new:
                while not self.ready:
                    time.sleep(0.5)
                print(f"Resending _ready_ event to module {module}...")
                for db in dataitems:
                    for f in dir(db):
                        if f.startswith("_") and f[-1] == "_" and f[1] != "_":
                            func = getattr(db, f, None)
                            if callable(func):
                                self.events.append(f, func)
                    for e in ("_bot_ready_", "_ready_"):
                        func = getattr(db, e, None)
                        if callable(func):
                            await_fut(create_future(func, bot=self, priority=True), priority=True)
            print(f"Successfully loaded module {module}.")

    def unload(self, mod=None):
        if mod is None:
            mods = deque(self.categories)
        else:
            mod = mod.casefold()
            if mod not in self.categories:
                raise KeyError
            mods = [mod]
        for mod in mods:
            for command in self.categories[mod]:
                command.unload()
            for database in self.dbitems[mod]:
                database.unload()
            self.categories.pop(mod)
            self.dbitems.pop(mod)
            self.size.pop(mod)

    def reload(self, mod=None):
        if not mod:
            sub_kill()
            modload = deque()
            files = [i for i in os.listdir("commands") if is_code(i)]
            for f in files:
                modload.append(create_future_ex(self.get_module, f, priority=True))
            return [fut.result() for fut in modload]           
        return self.get_module(mod + ".py")

    # Loads all modules in the commands folder and initializes bot commands and databases.
    def get_modules(self):
        files = [i for i in os.listdir("commands") if is_code(i)]
        self.categories = fcdict()
        self.dbitems = fcdict()
        self.commands = fcdict()
        self.database = fcdict()
        self.data = fcdict()
        self.size = fcdict()
        for f in os.listdir():
            if is_code(f):
                self.size[f] = line_count(f)
        self.modload = deque()
        for f in files:
            self.modload.append(create_future(self.get_module, f, priority=True))
        self.loaded = True

    # Autosaves modified bot databases. Called once every minute and whenever the bot is about to shut down.
    def update(self):
        self.update_embeds()
        saved = alist()
        with tracebacksuppressor:
            for i in self.database:
                u = self.database[i]
                if getattr(u, "update", None) is not None:
                    if u.update(True):
                        saved.append(i)
        # if saved:
        #     print("Autosaved " + str(saved) + ".")

    zw_callback = zwencode("callback")

    # Operates on reactions on special messages, calling the _callback_ methods of commands when necessary.
    async def react_callback(self, message, reaction, user):
        if message.author.id == self.id:
            if self.closed:
                return
            u_perm = self.get_perms(user.id, message.guild)
            if u_perm <= -inf:
                return
            msg = message.content.strip("*")
            if not msg and message.embeds:
                msg = str(message.embeds[0].description).strip("*")
            if msg[:3] != "```" or len(msg) <= 3:
                msg = None
                if message.embeds:
                    s = message.embeds[0].footer.text
                    if is_zero_enc(s):
                        msg = s
                if not msg:
                    return
            else:
                msg = msg[3:]
                while msg.startswith("\n"):
                    msg = msg[1:]
                check = "callback-"
                with suppress(ValueError):
                    msg = msg[:msg.index("\n")]
                if not msg.startswith(check):
                    return
            while len(self.react_sem) > 65536:
                self.react_sem.pop(next(iter(self.react_sem)))
            while utc() - self.react_sem.get(message.id, 0) < 30:
                # Ignore if more than 2 reactions already queued for target message
                if self.react_sem.get(message.id, 0) - utc() > 1:
                    return
                await asyncio.sleep(0.2)
            if reaction is not None:
                reacode = str(reaction).encode("utf-8")
            else:
                reacode = None
            msg = message.content.strip("*")
            if not msg and message.embeds:
                msg = str(message.embeds[0].description).strip("*")
            if msg[:3] != "```" or len(msg) <= 3:
                msg = None
                if message.embeds:
                    s = message.embeds[0].footer.text
                    if is_zero_enc(s):
                        msg = s
                if not msg:
                    return
                # Experimental zero-width invisible character encoded message (unused)
                try:
                    msg = msg[msg.index(self.zw_callback) + len(self.zw_callback):]
                except ValueError:
                    return
                msg = zwdecode(msg)
                args = msg.split("q")
            else:
                msg = msg[3:]
                while msg[0] == "\n":
                    msg = msg[1:]
                check = "callback-"
                msg = msg.split("\n")[0]
                msg = msg[len(check):]
                args = msg.split("-")
            catn, func, vals = args[:3]
            func = func.casefold()
            argv = "-".join(args[3:])
            catg = self.categories[catn]
            # Force a rate limit on the reaction processing for the message
            self.react_sem[message.id] = max(utc(), self.react_sem.get(message.id, 0) + 1)
            for f in catg:
                if f.__name__.casefold() == func:
                    async with ExceptionSender(message.channel):
                        timeout = getattr(f, "_timeout_", 1) * self.timeout
                        if timeout >= inf:
                            timeout = None
                        await asyncio.wait_for(
                            f._callback_(
                                message=message,
                                channel=message.channel,
                                guild=message.guild,
                                reaction=reacode,
                                user=user,
                                perm=u_perm,
                                vals=vals,
                                argv=argv,
                                bot=self,
                            ),
                            timeout=timeout)
                        break
            self.react_sem.pop(message.id, None)

    # Handles all updates to the bot. Manages the bot's status and activity on discord, and updates all databases.
    async def handle_update(self, force=False):
        if utc() - self.last_check > 0.5 or force:
            semaphore = self.semaphore if not force else emptyctx
            with suppress(SemaphoreOverflowError):
                with semaphore:
                    self.last_check = utc()
                    if not force:
                        create_task(self.get_state())
                    with tracebacksuppressor:
                        guild_count = len(self.guilds)
                        changed = guild_count != self.guild_count
                        if changed or utc() > self.stat_timer:
                            # Status changes every 12-21 seconds
                            self.stat_timer = utc() + float(frand(5)) + 8
                            self.guild_count = guild_count
                            self.status_iter = (self.status_iter + 1) % 3
                            with suppress(discord.NotFound):
                                u = await self.fetch_user(next(iter(self.owners)))
                                n = u.name
                                text = f"live to {uni_str(guild_count)} server{'s' if guild_count != 1 else ''}, from {uni_str(n)}'{'s' if n[-1] != 's' else ''} place!"
                                activity = discord.Streaming(name=text, url=self.website)
                                activity.game = self.website
                                if changed:
                                    print(repr(activity))
                                # Status iterates through 3 possible choices
                                status = self.statuses[self.status_iter]
                                await self.change_presence(activity=activity, status=status)
                                # Member update events are not sent through for the current user, so manually send a _seen_ event
                                await self.seen(self.user, event="misc", raw="Changing their status")
                    # Update databases
                    for u in self.database.values():
                        if utc() - u.used > u.rate_limit or force:
                            create_future(u, priority=True)
                            create_task(self.garbage_collect(u))

    # Processes a message, runs all necessary commands and bot events. May be called from another source.
    async def process_message(self, message, msg, edit=True, orig=None, cb_argv=None, loop=False):
        if self.closed:
            return
        cpy = msg
        # Strip quote from message.
        if msg[:2] == "> ":
            msg = msg[2:]
        # Strip spoiler from message.
        elif msg[:2] == "||" and msg[-2:] == "||":
            msg = msg[2:-2]
        # Strip code boxes from message.
        msg = msg.replace("`", "").strip()
        # Get user, channel, guild that the message belongs to
        user = message.author
        guild = message.guild
        u_id = user.id
        channel = message.channel
        c_id = channel.id
        if guild:
            g_id = guild.id
        else:
            g_id = 0
        # Get list of enabled commands for the channel.
        if g_id:
            try:
                enabled = self.data.enabled[c_id]
            except KeyError:
                enabled = ("main", "string", "admin")
        else:
            enabled = frozenset(self.categories)
        u_perm = self.get_perms(u_id, guild)
        admin = not inf > u_perm
        # Gets prefix for current guild.
        if u_id == self.id:
            prefix = self.prefix
        else:
            prefix = self.get_prefix(guild)
        op = False
        comm = msg
        # Mentioning the bot serves as an alias for the prefix.
        for check in self.mention:
            if comm.startswith(check):
                prefix = self.prefix
                comm = comm[len(check):].strip()
                op = True
                break
        if comm.startswith(prefix):
            comm = comm[len(prefix):].strip()
            op = True
        # Respond to blacklisted users attempting to use a command, or when mentioned without a command.
        if (u_perm <= -inf and (op or self.id in (member.id for member in message.mentions))):
            # print(f"Ignoring command from blacklisted user {user} ({u_id}): {lim_str(message.content, 256)}")
            create_task(send_with_react(
                channel,
                "Sorry, you are currently not permitted to request my services.",
                reacts="❎",
            ))
            return
        if self.id in (member.id for member in message.mentions):
            try:
                await self.send_event("_mention_", user=user, message=message, msg=msg, exc=True)
            except (RuntimeError, StopIteration):
                return
        remaining = 0
        run = False
        if op:
            # Special case: the ? alias for the ~help command, since ? is an argument flag indicator and will otherwise be parsed as one.
            if len(comm) and comm[0] == "?":
                command_check = comm[0]
                i = 1
            else:
                # Parse message to find command.
                i = len(comm)
                for end in " ?-+\t\n":
                    if end in comm:
                        i2 = comm.index(end)
                        if i2 < i:
                            i = i2
                command_check = full_prune(comm[:i]).replace("*", "").replace("_", "").replace("||", "")
            # Hash table lookup for target command: O(1) average time complexity.
            if command_check in bot.commands:
                # Multiple commands may have the same alias, run all of them
                for command in bot.commands[command_check]:
                    # Make sure command is enabled, administrators bypass this
                    if full_prune(command.catg) in enabled or admin:
                        # argv is the raw parsed argument data
                        argv = comm[i:].strip()
                        run = True
                        print(f"{getattr(guild, 'id', 0)}: {user} ({u_id}) issued command {msg}")
                        req = command.min_level
                        fut = None
                        try:
                            # Make sure server-only commands can only be run in servers.
                            if guild is None:
                                if getattr(command, "server_only", False):
                                    raise ReferenceError("This command is only available in servers.")
                            # Make sure target has permission to use the target command, rate limit the command if necessary.
                            if u_perm is not nan:
                                if not u_perm >= req:
                                    raise command.perm_error(u_perm, req, "for command " + command_check)
                                x = command.rate_limit
                                if x:
                                    if issubclass(type(x), collections.abc.Sequence):
                                        x = x[not self.is_trusted(getattr(guild, "id", 0))]
                                    remaining += x
                                    d = command.used
                                    t = d.get(u_id, -inf)
                                    wait = utc() - t - x
                                    if wait > -1:
                                        if wait < 0:
                                            w = max(0.2, -wait)
                                            d[u_id] = max(t, utc()) + w
                                            await asyncio.sleep(w)
                                        if len(d) >= 4096:
                                            d.pop(next(iter(d)))
                                        d[u_id] = max(t, utc())
                                    else:
                                        raise TooManyRequests(f"Command has a rate limit of {sec2time(x)}; please wait {sec2time(-wait)}.")
                            flags = {}
                            if cb_argv is not None:
                                argv = cb_argv
                                if loop:
                                    inc_dict(flags, h=1)
                            if argv:
                                # Commands by default always parse unicode fonts as regular text unless otherwise specified.
                                if not hasattr(command, "no_parse"):
                                    argv = unicode_prune(argv)
                                argv = argv.strip()
                                # Parse command flags (this is a bit of a mess)
                                if hasattr(command, "flags"):
                                    flaglist = command.flags
                                    for q in "?-+":
                                        if q in argv:
                                            for char in flaglist:
                                                flag = q + char
                                                for r in (flag, flag.upper()):
                                                    while len(argv) >= 4 and r in argv:
                                                        found = False
                                                        i = argv.index(r)
                                                        if i == 0 or argv[i - 1] == " " or argv[i - 2] == q:
                                                            with suppress(IndexError, KeyError):
                                                                if argv[i + 2] == " " or argv[i + 2] == q:
                                                                    argv = argv[:i] + argv[i + 2:]
                                                                    add_dict(flags, {char: 1})
                                                                    found = True
                                                        if not found:
                                                            break
                                        if q in argv:
                                            for char in flaglist:
                                                flag = q + char
                                                for r in (flag, flag.upper()):
                                                    while len(argv) >= 2 and r in argv:
                                                        found = False
                                                        for check in (r + " ", " " + r):
                                                            if check in argv:
                                                                argv = argv.replace(check, "")
                                                                add_dict(flags, {char: 1})
                                                                found = True
                                                        if argv == r:
                                                            argv = ""
                                                            add_dict(flags, {char: 1})
                                                            found = True
                                                        if not found:
                                                            break
                            if argv:
                                argv = argv.strip()
                            argl = None
                            # args is a list of arguments parsed from argv, using shlex syntax when possible.
                            if not argv:
                                args = []
                            else:
                                # Used as a goto lol
                                with suppress(StopIteration):
                                    brackets = {"<": ">", "(": ")", "[": "]", "{": "}"}
                                    for x, y in brackets.items():
                                        if x in argv and y in argv:
                                            xi = argv.index(x)
                                            yi = argv.rindex(y)
                                            if xi < yi:
                                                if hasattr(command, "multi"):
                                                    argv2 = single_space((argv[:xi] + " " + argv[yi + 1:]).replace("\n", " ").replace(",", " ").replace("\t", " ")).strip()
                                                    argv3 = single_space(argv[xi + 1:yi].replace("\n", " ").replace(",", " ").replace("\t", " ")).strip()
                                                    try:
                                                        argl = shlex.split(argv3)
                                                    except ValueError:
                                                        argl = argv3.split()
                                                else:
                                                    argv2 = single_space(argv[:xi].replace("\n", " ").replace("\t", " ") + " " + (argv[xi + 1:yi]).replace("\n", " ").replace(",", " ").replace("\t", " ") + " " + argv[yi + 1:].replace("\n", " ").replace("\t", " "))
                                                try:
                                                    args = shlex.split(argv2)
                                                except ValueError:
                                                    args = argv2.split()
                                                raise StopIteration
                                    argv2 = single_space(argv.replace("\n", " ").replace("\t", " "))
                                    try:
                                        args = shlex.split(argv2)
                                    except ValueError:
                                        args = argv2.split()
                                    if args and getattr(command, "flags", None):
                                        if not ("a" in flags or "e" in flags or "d" in flags):
                                            if "a" in command.flags and "e" in command.flags and "d" in command.flags:
                                                if args[0] in ("add", "enable", "set"):
                                                    args.pop(0)
                                                    add_dict(flags, {"a": 1})
                                                elif args[0] in ("rem", "disable", "remove", "unset"):
                                                    args.pop(0)
                                                    add_dict(flags, {"d": 1})
                            # Assign "guild" as an object that mimics the discord.py guild if there is none
                            if guild is None:
                                guild = self.UserGuild(
                                    user=user,
                                    channel=channel,
                                )
                                channel = guild.channel
                            # Automatically start typing if the command is time consuming
                            tc = getattr(command, "time_consuming", False)
                            if not loop and tc:
                                fut = create_task(channel.trigger_typing())
                            # Send bot event: user has executed command
                            await self.send_event("_command_", user=user, command=command)
                            # Get maximum time allowed for command to process
                            timeout = getattr(command, "_timeout_", 1) * bot.timeout
                            if timeout >= inf:
                                timeout = None
                            # Create a future to run the command
                            future = create_future(
                                command,                        # command is a callable object, may be async or not
                                bot=bot,                        # for interfacing with bot's database
                                argv=argv,                      # raw text argument
                                args=args,                      # split text arguments
                                argl=argl,                      # inputted array of arguments
                                flags=flags,                    # special flags
                                perm=u_perm,                    # permission level
                                user=user,                      # user that invoked the command
                                message=message,                # message data
                                channel=channel,                # channel data
                                guild=guild,                    # guild data
                                name=command_check,                     # alias the command was called as
                                callback=self.process_message,  # function that called the command
                                timeout=timeout,                # timeout delay for the command
                            )
                            # Add a callback to typing in the channel if the command takes too long
                            if fut is None and not hasattr(command, "typing"):
                                create_task(delayed_callback(future, 2, typing, channel))
                            response = await future
                            # Process response to command if there is one
                            if response is not None:
                                if fut is not None:
                                    await fut
                                # Raise exceptions returned by the command
                                if issubclass(type(response), Exception):
                                    raise response
                                elif bool(response) is not False:
                                    # If 2-tuple returned, send as message-react pair
                                    if type(response) is tuple and len(response) == 2:
                                        response, react = response
                                        if react == 1:
                                            react = "❎"
                                    else:
                                        react = False
                                    sent = None
                                    # Process list as a sequence of messages to send
                                    if type(response) is list:
                                        for r in response:
                                            async with delay(1 / 3):
                                                create_task(channel.send(r))
                                    # Process dict as kwargs for a message send
                                    elif issubclass(type(response), collections.abc.Mapping):
                                        if "file" in response:
                                            sent = await send_with_file(channel, response.get("content", ""), **response)
                                        else:
                                            sent = await channel.send(**response)
                                    else:
                                        if type(response) not in (str, bytes, bytearray):
                                            response = str(response)
                                        # Process everything else as a string
                                        if type(response) is str and len(response) <= 2000:
                                            sent = await channel.send(response)
                                        else:
                                            # Send a file if the message is too long
                                            if type(response) is not bytes:
                                                response = bytes(str(response), "utf-8")
                                                filemsg = "Response too long for message."
                                            else:
                                                filemsg = "Response data:"
                                            if len(response) <= guild.filesize_limit:
                                                b = io.BytesIO(response)
                                                f = discord.File(b, filename="message.txt")
                                                sent = await send_with_file(channel, filemsg, f)
                                            else:
                                                raise OverflowError("Response too long for file upload.")
                                    # Add targeted react if there is one
                                    if react and sent:
                                        await sent.add_reaction(react)
                        # Represents any timeout error that occurs
                        except (T0, T1, T2):
                            if fut is not None:
                                await fut
                            print(msg)
                            raise TimeoutError("Request timed out.")
                        except (ArgumentError, TooManyRequests) as ex:
                            if fut is not None:
                                await fut
                            create_task(send_exception(channel, ex))
                            return
                        # Represents all other errors
                        except Exception as ex:
                            if fut is not None:
                                await fut
                            print_exc()
                            create_task(send_exception(channel, ex))
        # If message was not processed as a command, send a _nocommand_ event with the parsed message data.
        if not run and u_id != bot.id:
            temp = to_alphanumeric(cpy).casefold()
            await self.send_event("_nocommand_", text=temp, edit=edit, orig=orig, msg=msg, message=message, perm=u_perm)
        # Return the delay before the message can be called again. This is calculated by the rate limit of the command.
        return remaining

    # Adds a webhook to the bot's user and webhook cache.
    def add_webhook(self, w):
        user = self.GhostUser()
        user.id = w.id
        user.name = w.name
        user.display_name = w.name
        user.joined_at = w.created_at
        user.avatar = w.avatar
        user.avatar_url = w.avatar_url
        user.bot = True
        user.send = w.send
        user.dm_channel = w.channel
        user.webhook = w
        self.cache.users[w.id] = user
        self.limit_cache("users")
        if w.token:
            webhooks = set_dict(self.cw_cache, w.channel.id, cdict())
            webhooks[w.id] = user
            user.semaphore = Semaphore(5, 256, delay=0.3, rate_limit=5)
        return user

    async def fetch_webhooks(self, guild):
        member = guild.get_member(self.id)
        if member and member.guild_permissions.manage_webhooks:
            return await aretry(guild.webhooks, attempts=3, delay=15, exc=(discord.Forbidden, discord.NotFound))
        raise PermissionError

    # Loads all webhooks in the target channel.
    async def load_channel_webhooks(self, channel, force=False, bypass=False):
        if channel.id in self.cw_cache and not force:
            return self.cw_cache[channel.id].values()
        async with self.guild_semaphore if not bypass else emptyctx:
            self.cw_cache.pop(channel.id, None)
            if not channel.permissions_for(channel.guild.get_member(self.id)).manage_webhooks:
                raise PermissionError("Not permitted to create webhooks in channel.")
            webhooks = await aretry(channel.webhooks, attempts=5, delay=15, exc=(discord.Forbidden, discord.NotFound))
        return [self.add_webhook(w) for w in webhooks]

    # Loads all webhooks in the target guild.
    async def load_guild_webhooks(self, guild):
        with tracebacksuppressor:
            try:
                async with self.guild_semaphore:
                    webhooks = await self.fetch_webhooks(guild)
            except (PermissionError, discord.Forbidden, discord.NotFound):
                for channel in guild.text_channels:
                    with suppress(PermissionError, discord.Forbidden, discord.NotFound):
                        await self.load_channel_webhooks(channel)
            else:
                return [self.add_webhook(w) for w in webhooks]

    # Gets a valid webhook for the target channel, creating a new one when necessary.
    async def ensure_webhook(self, channel, force=False, bypass=False):
        wlist = await self.load_channel_webhooks(channel, force=force, bypass=bypass)
        if not wlist:
            w = await channel.create_webhook(name=self.name, reason="Auto Webhook")
            w = self.add_webhook(w)
        else:
            w = choice(wlist)
        return w

    # Sends a message to the target channel, using a random webhook from that channel.
    async def send_as_webhook(self, channel, *args, **kwargs):
        w = await self.ensure_webhook(channel, bypass=True)
        kwargs.pop("wait", None)
        reacts = kwargs.pop("reacts", None)
        try:
            async with w.semaphore:
                message = await w.send(*args, wait=True, **kwargs)
        except (discord.NotFound, discord.InvalidArgument, discord.Forbidden):
            w = await self.ensure_webhook(channel, force=True)
            async with w.semaphore:
                message = await w.send(*args, wait=True, **kwargs)
        await self.seen(self.user, event="message", count=len(kwargs.get("embeds", (None,))), raw=f"Sending a message, {channel.guild}")
        if reacts:
            for react in reacts:
                async with delay(1 / 3):
                    create_task(message.add_reaction(react))
        return message

    # Sends a list of embeds to the target sendable, using a webhook when possible.
    async def _send_embeds(self, sendable, embeds):
        s_id = verify_id(sendable)
        sendable = await self.fetch_messageable(s_id)
        async with ExceptionSender(sendable):
            if not embeds:
                return
            guild = getattr(sendable, "guild", None)
            # Determine whether to send embeds individually or as blocks of up to 10, based on whether it is possible to use webhooks
            single = False
            if guild is None or hasattr(guild, "ghost") or len(embeds) == 1:
                single = True
            else:
                m = guild.get_member(self.id)
                if m is None:
                    m = self.user
                    single = True
                else:
                    if not m.guild_permissions.manage_webhooks:
                        single = True
            if single:
                for emb in embeds:
                    async with delay(1 / 3):
                        reacts = None
                        if type(emb) is not discord.Embed:
                            reacts = emb.get("reacts")
                            emb = discord.Embed.from_dict(emb)
                        if reacts:
                            create_task(send_with_react(sendable, embed=emb, reacts=reacts))
                        else:
                            create_task(sendable.send(embed=emb))
                return
            embs = deque()
            reacts = discord.Embed.Empty
            for emb in embeds:
                if type(emb) is not discord.Embed:
                    embs.append(discord.Embed.from_dict(emb))
                    r = emb.get("reacts")
                    if reacts == discord.Embed.Empty:
                        reacts = r
                    if r == reacts:
                        continue
                else:
                    embs.append(emb)
                reacts = None
            await self.send_as_webhook(sendable, embeds=embs, username=m.display_name, avatar_url=best_url(m), reacts=reacts)

    # Adds embeds to the embed sender, waiting for the next update event.
    def send_embeds(self, channel, embeds=None, embed=None):
        if embeds is not None and not issubclass(type(embeds), collections.abc.Collection):
            embeds = (embeds,)
        if embed is not None:
            if embeds is not None:
                embeds += (embed,)
            else:
                embeds = (embed,)
        elif not embeds:
            return
        c_id = verify_id(channel)
        user = self.cache.users.get(c_id)
        if user is not None:
            create_task(self._send_embeds(user, embeds))
        else:
            embs = set_dict(self.embed_senders, c_id, [])
            embs.extend(embeds)

    def send_as_embeds(self, channel, description=None, fields=None, md=nofunc, author=None, footer=None, colour=None):
        if description is not None and type(description) is not str:
            if type(description) in (bytes, bytearray):
                description = description.decode("utf-8", "replace")
            else:
                description = str(description)
        if not description and not fields:
            return
        col = 0 if colour is None else colour if not issubclass(type(colour), collections.abc.Sequence) else colour[0]
        off = 128 if not issubclass(type(colour), collections.abc.Sequence) else colour[1]
        embs = deque()
        emb = discord.Embed(colour=colour2raw(hue2colour(col)))
        if description:
            # Separate text into paragraphs, then lines, then words, then characters and attempt to add them one at a time, adding extra embeds when necessary
            curr = ""
            if "\n\n" in description:
                paragraphs = alist(p + "\n\n" for p in description.split("\n\n"))
            else:
                paragraphs = alist((description,))
            while paragraphs:
                para = paragraphs.popleft()
                if len(para) > 2000:
                    temp = para[:2000]
                    try:
                        i = temp.rindex("\n")
                        s = "\n"
                    except ValueError:
                        try:
                            i = temp.rindex(" ")
                            s = " "
                        except ValueError:
                            paragraphs.appendleft(para[2000:])
                            paragraphs.appendleft(temp)
                            continue
                    paragraphs.appendleft(para[i + 1:])
                    paragraphs.appendleft(para[:i] + s)
                    continue
                if not embs:
                    if author:
                        emb.set_author(**author)
                if len(curr) + len(para) > 2000:
                    emb.description = md(curr.strip())
                    curr = para
                    embs.append(emb)
                    col += 128
                    emb = discord.Embed(colour=colour2raw(hue2colour(col)))
                else:
                    curr += para
            if curr:
                emb.description = md(curr.strip())
        if fields:
            for field in fields:
                if issubclass(type(field), collections.abc.Mapping):
                    field = tuple(field.values())
                elif not issubclass(type(field), collections.abc.Sequence):
                    field = tuple(field)
                n = lim_str(field[0], 256)
                v = lim_str(md(field[1]), 1024)
                i = True if len(field) < 3 else field[2]
                if len(emb) + len(n) + len(v) > 6000 or len(emb.fields) > 24:
                    embs.append(emb)
                    col += 128
                    emb = discord.Embed(colour=colour2raw(hue2colour(col)))
                emb.add_field(name=n, value=v if v else "\u200b", inline=i)
        if len(emb):
            embs.append(emb)
        if footer and embs:
            embs[-1].set_footer(**footer)
        self.send_embeds(channel, embeds=embs)

    # Updates all embed senders.
    def update_embeds(self):
        sent = False
        for s_id in self.embed_senders:
            embeds = self.embed_senders[s_id]
            embs = deque()
            for emb in embeds:
                # Send embeds in groups of up to 10, up to 6000 characters
                if len(embs) > 9 or len(emb) + sum(len(e) for e in embs) > 6000:
                    break
                embs.append(emb)
            # Left over embeds are placed back in embed sender
            self.embed_senders[s_id] = embeds = embeds[len(embs):]
            if not embeds:
                self.embed_senders.pop(s_id)
            create_task(self._send_embeds(s_id, embs))
            sent = True
        return sent

    # The fast update loop that runs 24 times per second. Used for events where timing is important.
    def fast_loop(self):

        async def event_call(freq):
            for i in range(freq):
                async with delay(1 / freq):
                    await self.send_event("_call_")

        freq = 24
        sent = 0
        while not self.closed:
            with tracebacksuppressor:
                sent = self.update_embeds()
                if sent:
                    await_fut(event_call(freq), delay=0.005, priority=True)
                else:
                    with delay(1 / freq):
                        await_fut(self.send_event("_call_"), delay=0.001, priority=True)

    # The lazy update loop that runs once every 2-4 seconds. Calls the bot database autosave event once every ~60 seconds.
    async def slow_loop(self):
        autosave = 0
        while not self.closed:
            async with delay(frand(2) + 2):
                async with tracebacksuppressor:
                    if utc() - autosave > 60:
                        autosave = utc()
                        await create_future(self.update, priority=True)
                        await create_future(self.update_from_client, priority=True)
                    while self.blocked > 0:
                        print("Update event blocked.")
                        self.blocked -= 1
                        await asyncio.sleep(1)
                    await self.handle_update()

    # User seen event
    seen = lambda self, user, delay=0, event=None, **kwargs: create_task(self.send_event("_seen_", user=user, delay=delay, event=event, **kwargs))

    # Deletes own messages if any of the "X" emojis are reacted by a user with delete message permission level, or if the message originally contained the corresponding reaction from the bot.
    async def check_to_delete(self, message, reaction, user):
        if message.author.id == self.id or message.author.id in self.cw_cache.get(message.channel.id, ()):
            with suppress(discord.NotFound):
                u_perm = self.get_perms(user.id, message.guild)
                check = False
                if not u_perm < 3:
                    check = True
                else:
                    for react in message.reactions:
                        if str(reaction) == str(react):
                            users = await react.users().flatten()
                            for u in users:
                                if u.id == self.id:
                                    check = True
                                    break
                if check and user.id != self.id:
                    s = str(reaction)
                    if s in "❌✖️🇽❎":
                        await self.silent_delete(message, exc=True)

    # Handles a new sent message, calls process_message and sends an error if an exception occurs.
    async def handle_message(self, message, edit=True):
        cpy = msg = message.content
        async with ExceptionSender(message.channel):
            if msg and msg[0] == "\\":
                cpy = msg[1:]
            await self.process_message(message, cpy, edit, msg)

    def set_classes(self):
        bot = self

        # For compatibility with guild objects, takes a user and DM channel.
        class UserGuild(discord.Object):

            class UserChannel(discord.abc.PrivateChannel):

                def __init__(self, channel, **void):
                    self.channel = channel

                def __dir__(self):
                    data = set(object.__dir__(self))
                    data.update(dir(self.channel))
                    return data

                def __getattr__(self, key):
                    with suppress(AttributeError):
                        return self.__getattribute__(key)
                    return getattr(self.__getattribute__("channel"), key)

                def fetch_message(self, id):
                    return bot.fetch_message(id, self.channel)

                me = bot.user
                name = "DM"
                topic = None
                is_nsfw = lambda: True
                is_news = lambda: False

            def __init__(self, user, channel, **void):
                self.channel = self.system_channel = self.rules_channel = self.UserChannel(channel)
                self.members = [user, bot.user]
                self._members = {m.id: m for m in self.members}
                self.channels = self.text_channels = [self.channel]
                self.voice_channels = []
                self.roles = []
                self.emojis = []
                self.get_channel = lambda *void1, **void2: self.channel
                self.owner_id = bot.id
                self.owner = bot.user
                self.fetch_member = bot.fetch_user
                self.get_member = lambda *void1, **void2: None
                self.voice_client = None

            def __dir__(self):
                data = set(object.__dir__(self))
                data.update(dir(self.channel))
                return data

            def __getattr__(self, key):
                with suppress(AttributeError):
                    return self.__getattribute__(key)
                return getattr(self.__getattribute__("channel"), key)

            filesize_limit = 8388608
            bitrate_limit = 98304
            emoji_limit = 0
            large = False
            description = ""
            max_members = 2
            unavailable = False
            ghost = True

        # Represents a deleted/not found user.
        class GhostUser(discord.abc.Snowflake):
            
            def __init__(self):
                self.id = 0
                self.name = "[USER DATA NOT FOUND]"
                self.discriminator = "0000"
                self.avatar = ""
                self.avatar_url = ""
                self.bot = False
                self.display_name = ""

            __repr__ = lambda self: f"<Ghost User id={self.id} name='{self.name}' discriminator='{self.discriminator}' bot=False>"
            __str__ = lambda self: f"{self.name}#{self.discriminator}"
            system = False
            history = lambda *void1, **void2: async_nop()
            dm_channel = None
            create_dm = lambda self: async_nop()
            relationship = None
            is_friend = lambda self: None
            is_blocked = lambda self: None
            colour = color = discord.Colour(16777215)
    
            @property
            def mention(self):
                return f"<@{self.id}>"

            @property
            def created_at(self):
                return snowflake_time(self.id)

            ghost = True

        # Represents a deleted/not found message.
        class GhostMessage(discord.abc.Snowflake):

            content = bold(css_md(uni_str("[MESSAGE DATA NOT FOUND]")))
            
            def __init__(self):
                self.author = bot.get_user(bot.deleted_user)
                self.channel = None
                self.guild = None
                self.id = 0

            async def delete(self, *void1, **void2):
                pass

            __repr__ = lambda self: self.system_content if self.system_content else self.content
            tts = False
            type = "default"
            nonce = False
            embeds = ()
            call = None
            mention_everyone = False
            mentions = ()
            webhook_id = None
            attachments = ()
            pinned = False
            flags = None
            reactions = ()
            activity = None
            clean_content = ""
            system_content = ""
            edited_at = None
            jump_url = "https://discord.com/channels/-1/-1/-1"
            is_system = lambda self: None

            @property
            def created_at(self):
                return snowflake_time(self.id)

            edit = delete
            publish = delete
            pin = delete
            unpin = delete
            add_reaction = delete
            remove_reaction = delete
            clear_reaction = delete
            clear_reactions = delete
            ack = delete
            ghost = True

        bot.UserGuild = UserGuild
        bot.GhostUser = GhostUser
        bot.GhostMessage = GhostMessage
    
    def set_client_events(self):

        print("Setting client events...")

        # The event called when the bot starts up.
        @self.event
        async def on_ready():
            print("Successfully connected as " + str(self.user))
            self.mention = (user_mention(self.id), user_pc_mention(self.id))
            with tracebacksuppressor:
                futs = set()
                futs.add(create_task(self.get_state()))
                print("Servers: ")
                for guild in self.guilds:
                    if guild.unavailable:
                        print(f"> Guild {guild.id} is not available.")
                    else:
                        print("> " + guild.name)
                await self.handle_update()
                futs.add(create_future(self.update_from_client, priority=True))
                futs.add(create_future(self.update_from_guilds, priority=True))
                create_task(self.get_ip())
                if not self.started:
                    self.started = True
                    print("Loading imported modules...")
                    # Wait until all modules have been loaded successfully
                    while self.modload:
                        fut = self.modload.popleft()
                        with tracebacksuppressor:
                            print(fut)
                            mod = await fut
                    print("Command aliases:")
                    print(self.commands)
                    # Assign all bot database events to their corresponding keys.
                    for u in self.database.values():
                        for f in dir(u):
                            if f.startswith("_") and f[-1] == "_" and f[1] != "_":
                                func = getattr(u, f, None)
                                if callable(func):
                                    self.events.append(f, func)
                    print("Database events:")
                    print(self.events)
                    for fut in futs:
                        await fut
                    await self.fetch_user(self.deleted_user)
                    # Set bot avatar if none has been set.
                    if not os.path.exists("misc/init.tmp"):
                        print("Setting bot avatar...")
                        f = await create_future(open, "misc/avatar.png", "rb", priority=True)
                        with closing(f):
                            b = await create_future(f.read, priority=True)
                        await self.user.edit(avatar=b)
                        await self.seen(self.user, event="misc", raw="Editing their profile")
                        touch("misc/init.tmp")
                    create_task(self.slow_loop())
                    create_thread(self.fast_loop)
                    print("Update loops initiated.")
                    # Load all webhooks from cached guilds.
                    futs = deque(create_task(self.load_guild_webhooks(guild)) for guild in self.guilds)
                    print("Bot ready.")
                    # Send bot_ready event to all databases.
                    await self.send_event("_bot_ready_", bot=self)
                    for fut in futs:
                        await fut
                    self.ready = True
                    # Send ready event to all databases.
                    await self.send_event("_ready_", bot=self)
                    print("Initialization complete.")
                else:
                    for fut in futs:
                        await fut
                    print("Reinitialized.")

        # Server join message
        @self.event
        async def on_guild_join(guild):
            create_task(self.load_guild_webhooks(guild))
            print("New server: " + str(guild))
            g = await self.fetch_guild(guild.id)
            m = guild.get_member(self.id)
            await self.send_event("_join_", user=m, guild=g)
            channel = await self.get_first_sendable(g, m)
            emb = discord.Embed(colour=discord.Colour(8364031))
            emb.set_author(**get_author(self.user))
            emb.description = f"Hi there! I'm {self.name}, a multipurpose discord bot created by <@201548633244565504>. Thanks for adding me"
            user = None
            with suppress(discord.Forbidden):
                a = await guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add).flatten()
                for e in a:
                    if e.target.id == self.id:
                        user = e.user
                        break
            if user is not None:
                emb.description += f", {user_mention(user.id)}"
            emb.description += (
                f"!\nMy default prefix is `{self.prefix}`, which can be changed as desired on a per-server basis. Mentioning me also serves as an alias for all prefixes.\n"
                + f"For more information, use the `{self.prefix}help` command, and my source code is available at {self.website} for those who are interested.\n"
                + "Pleased to be at your service 🙂"
            )
            if not m.guild_permissions.administrator:
                emb.add_field(name="Psst!", value=(
                    "I noticed you haven't given me administrator permissions here.\n"
                    + "That's completely understandable if intentional, but please note that without the required permissions, some features may not function well, or not at all."
                ))
            await channel.send(embed=emb)

        # Reaction add event: uses raw payloads rather than discord.py message cache. calls _seen_ bot database event.
        @self.event
        async def on_raw_reaction_add(payload):
            try:
                channel = await self.fetch_channel(payload.channel_id)
                user = await self.fetch_user(payload.user_id)
                message = await self.fetch_message(payload.message_id, channel=channel)
            except discord.NotFound:
                return
            raw = "Adding a reaction"
            if getattr(channel, "guild", None) is not None:
                raw += f", {channel.guild}"
            await self.seen(user, event="reaction", raw=raw)
            if user.id != self.id:
                reaction = str(payload.emoji)
                await self.react_callback(message, reaction, user)
                await self.check_to_delete(message, reaction, user)

        # Reaction remove event: uses raw payloads rather than discord.py message cache. calls _seen_ bot database event.
        @self.event
        async def on_raw_reaction_remove(payload):
            try:
                channel = await self.fetch_channel(payload.channel_id)
                user = await self.fetch_user(payload.user_id)
                message = await self.fetch_message(payload.message_id, channel=channel)
            except discord.NotFound:
                return
            raw = "Adding a reaction"
            if getattr(channel, "guild", None) is not None:
                raw += f", {channel.guild}"
            await self.seen(user, event="reaction", raw=raw)
            if user.id != self.id:
                reaction = str(payload.emoji)
                await self.react_callback(message, reaction, user)
                await self.check_to_delete(message, reaction, user)

        # Voice state update event: automatically unmutes self if server muted, calls _seen_ bot database event.
        @self.event
        async def on_voice_state_update(member, before, after):
            if member.id == self.id:
                after = member.voice
                if after is not None:
                    if after.mute or after.deaf:
                        # print("Unmuted self in " + member.guild.name)
                        await member.edit(mute=False, deafen=False)
                    await self.handle_update()
            # Check for users with a voice state.
            if after is not None and not after.afk:
                if before is None:
                    await self.seen(member, event="misc", raw=f"Joining a voice channel, {member.guild}")
                elif any((getattr(before, attr) != getattr(after, attr) for attr in ("self_mute", "self_deaf", "self_stream", "self_video"))):
                    await self.seen(member, event="misc", raw=f"Updating their voice settings, {member.guild}")

        # Typing event: calls _typing_ and _seen_ bot database events.
        @self.event
        async def on_typing(channel, user, when):
            await self.send_event("_typing_", channel=channel, user=user)
            raw = "Typing"
            if getattr(channel, "guild", None) is not None:
                raw += f", {channel.guild}"
            await self.seen(user, delay=10, event="typing", raw=raw)

        # Message send event: processes new message. calls _send_ and _seen_ bot database events.
        @self.event
        async def on_message(message):
            self.add_message(message)
            guild = message.guild
            if guild:
                create_task(self.send_event("_send_", message=message))
            raw = "Sending a message"
            if message.guild is not None:
                raw += f", {message.guild}"
            await self.seen(message.author, event="message", raw=raw)
            await self.react_callback(message, None, message.author)
            await self.handle_message(message, False)

        # Message edit event: processes edited message, uses raw payloads rather than discord.py message cache. calls _edit_ and _seen_ bot database events.
        @self.event
        async def on_raw_message_edit(payload):
            data = payload.data
            m_id = int(data["id"])
            raw = False
            if payload.cached_message:
                before = payload.cached_message
                after = await self.fetch_message(m_id, payload.message_id)
            else:
                try:
                    before = messages[m_id]
                except LookupError:
                    # If message was not in cache, create a ghost message object to represent old message.
                    c_id = data.get("channel_id")
                    if not c_id:
                        return
                    before = self.GhostMessage()
                    before.channel = channel = await self.fetch_channel(c_id)
                    before.guild = guild = getattr(channel, "guild", None)
                    before.id = payload.message_id
                    try:
                        u_id = data["author"]["id"]
                    except KeyError:
                        u_id = None
                        before.author = None
                    else:
                        if guild is not None:
                            user = guild.get_member(u_id)
                        else:
                            user = None
                        if not user:
                            user = await self.fetch_user(u_id)
                        before.author = user
                    try:
                        after = await channel.fetch_message(before.id)
                    except LookupError:
                        after = copy.copy(before)
                        after._update(data)
                    else:
                        before.author = after.author
                    raw = True
                else:
                    after = copy.copy(before)
                    after._update(data)
            self.add_message(after)
            if raw or before.content != after.content:
                await self.handle_message(after)
                if getattr(after, "guild", None):
                    create_task(self.send_event("_edit_", before=before, after=after))
                raw = "Editing a message"
                if after.guild is not None:
                    raw += f", {after.guild}"
                await self.seen(after.author, event="message", raw=raw)

        # Message delete event: uses raw payloads rather than discord.py message cache. calls _delete_ bot database event.
        @self.event
        async def on_raw_message_delete(payload):
            try:
                message = payload.cached_message
                if message is None:
                    raise LookupError
            except:
                channel = await self.fetch_channel(payload.channel_id)
                try:
                    message = await self.fetch_message(payload.message_id, channel)
                    if message is None:
                        raise LookupError
                except:
                    # If message was not in cache, create a ghost message object to represent old message.
                    message = self.GhostMessage()
                    message.channel = channel
                    try:
                        message.guild = channel.guild
                    except AttributeError:
                        message.guild = None
                    message.id = payload.message_id
                    message.author = await self.fetch_user(self.deleted_user)
            guild = message.guild
            if guild:
                await self.send_event("_delete_", message=message)

        # Message bulk delete event: uses raw payloads rather than discord.py message cache. calls _bulk_delete_ and _delete_ bot database events.
        @self.event
        async def on_raw_bulk_message_delete(payload):
            try:
                messages = payload.cached_messages
                if messages is None or len(messages) < len(payload.message_ids):
                    raise LookupError
            except:
                messages = set()
                channel = await self.fetch_channel(payload.channel_id)
                for m_id in payload.message_ids:
                    try:
                        message = await self.fetch_message(m_id, channel)
                        if message is None:
                            raise LookupError
                    except:
                        # If message was not in cache, create a ghost message object to represent old message.
                        message = self.GhostMessage()
                        message.channel = channel
                        try:
                            message.guild = channel.guild
                        except AttributeError:
                            message.guild = None
                        message.id = m_id
                        message.author = await self.fetch_user(self.deleted_user)
                    messages.add(message)
            messages = sorted(messages, key=lambda m: m.id)
            await self.send_event("_bulk_delete_", messages=messages)
            for message in messages:
                guild = getattr(message, "guild", None)
                if guild:
                    await self.send_event("_delete_", message=message, bulk=True)

        # User update event: calls _user_update_ and _seen_ bot database events.
        @self.event
        async def on_user_update(before, after):
            await self.send_event("_user_update_", before=before, after=after)
            await self.seen(after, event="misc", raw="Editing their profile")

        # Member update event: calls _member_update_ and _seen_ bot database events.
        @self.event
        async def on_member_update(before, after):
            await self.send_event("_member_update_", before=before, after=after)
            if self.status_changed(before, after):
                # A little bit of a trick to make sure this part is only called once per user event.
                # This is necessary because on_member_update is called once for every member object.
                # By fetching the first instance of a matching member object,
                # this ensures the event will not be called multiple times if the user shares multiple guilds with the bot.
                try:
                    member = self.get_member(after.id)
                except LookupError:
                    member = None
                if member is None or member.guild == after.guild:
                    if self.status_updated(before, after):
                        await self.seen(after, event="misc", raw="Changing their status")
                    elif after.status == discord.Status.offline:
                        await self.send_event("_offline_", user=after)

        # Member join event: calls _join_ and _seen_ bot database events.
        @self.event
        async def on_member_join(member):
            await self.send_event("_join_", user=member, guild=member.guild)
            await self.seen(member, event="misc", raw=f"Joining a server, {member.guild}")

        # Member leave event: calls _leave_ bot database event.
        @self.event
        async def on_member_remove(member):
            await self.send_event("_leave_", user=member, guild=member.guild)

        # Channel create event: calls _channel_create_ bot database event.
        @self.event
        async def on_guild_channel_create(channel):
            self.cache.channels[channel.id] = channel
            guild = channel.guild
            if guild:
                await self.send_event("_channel_create_", channel=channel, guild=guild)

        # Channel delete event: calls _channel_delete_ bot database event.
        @self.event
        async def on_guild_channel_delete(channel):
            print(channel, "was deleted from", channel.guild)
            guild = channel.guild
            if guild:
                await self.send_event("_channel_delete_", channel=channel, guild=guild)

        # Webhook update event: updates the bot's webhook cache if there are new webhooks.
        @self.event
        async def on_webhooks_update(channel):
            webhooks = await channel.webhooks()
            for w in tuple(self.cw_cache.get(channel.id, {}).values()):
                if w not in webhooks:
                    self.cw_cache[channel.id].pop(w.id)
                    self.cache.users.pop(w.id)
            for w in webhooks:
                self.add_webhook(w)

        # User ban event: calls _ban_ bot database event.
        @self.event
        async def on_member_ban(guild, user):
            print(user, "was banned from", guild)
            if guild:
                await self.send_event("_ban_", user=user, guild=guild)

        # Guild destroy event: Remove guild from bot cache.
        @self.event
        async def on_guild_remove(guild):
            self.cache.guilds.pop(guild.id, None)
            print(guild, "removed.")


# Queries for searching members
# Order of priority:
"""
ID (Full literal match)
Username + Discriminator (Full literal match)
Username (Full case-insensitive match)
Nickname (Full case-insensitive match)
Username + Discriminator (Full alphanumeric match)
Nickname (Full alphanumeric match)
Username + Discriminator (Starting literal match)
Username (Starting case-insensitive match)
Nickname (Starting case-insensitive match)
Username + Discriminator (Starting alphanumeric match)
Nickname (Starting alphanumeric match)
Username + Discriminator (Substring literal match)
Username (Substring case-insensitive match)
Nickname (Substring case-insensitive match)
Username + Discriminator (Substring alphanumeric match)
Nickname (Substring alphanumeric match)
"""
# Results are automatically sorted by match length, randomized if a tie occurs.

def userQuery1(x):
    yield x
    
def userIter1(x):
    yield str(x)

def userQuery2(x):
    yield str(x).casefold()

def userIter2(x):
    yield str(x)
    yield str(x.name).casefold()
    if getattr(x, "nick", None):
        yield str(x.nick).casefold()

def userQuery3(x):
    yield full_prune(x)

def userIter3(x):
    yield full_prune(x.name)
    if getattr(x, "nick", None):
        yield full_prune(x.nick)

def userQuery4(x):
    yield to_alphanumeric(x).replace(" ", "").casefold()

def userIter4(x):
    yield to_alphanumeric(x.name).replace(" ", "").casefold()
    if getattr(x, "nick", None):
        yield to_alphanumeric(x.nick).replace(" ", "").casefold()


# Heartbeat loop: Repeatedly deletes a file to inform the watchdog process that the bot's event loop is still running.
async def heartbeat_loop():
    print("Heartbeat Loop initiated.")
    with tracebacksuppressor:
        while not bot.closed:
            d = await delayed_coro(create_future(os.path.exists, bot.heartbeat, priority=True), 0.5)
            if d:
                with tracebacksuppressor(FileNotFoundError):
                    await create_future(os.remove, bot.heartbeat, priority=True)


# If this is the module being run and not imported, create a new Bot instance and run it.
if __name__ == "__main__":
    # Redirects all output to the main log manager (PRINT).
    _print = print
    with contextlib.redirect_stdout(PRINT):
        with contextlib.redirect_stderr(PRINT):
            PRINT.start()
            sys.stdout = sys.stderr = print = PRINT
            print("Logging started.")
            proc_start()
            miza = bot = client = Bot()
            miza.miza = miza
            create_task(heartbeat_loop())
            with miza:
                miza.run()
    print = _print
    sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__