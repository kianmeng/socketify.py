import cffi
from datetime import datetime
from enum import IntEnum
from http import cookies
import inspect
import json
import mimetypes
import os
from os import path
import platform
import signal
from threading import Thread, local, Lock
import uuid
from urllib.parse import parse_qs, quote_plus, unquote_plus

from .loop import Loop
from .status_codes import status_codes
from .helpers import static_route
from queue import SimpleQueue

mimetypes.init()


is_python = platform.python_implementation() == "CPython"

ffi = cffi.FFI()
ffi.cdef(
    """

struct us_socket_context_options_t {
    const char *key_file_name;
    const char *cert_file_name;
    const char *passphrase;
    const char *dh_params_file_name;
    const char *ca_file_name;
    const char *ssl_ciphers;
    int ssl_prefer_low_memory_usage;
};


struct us_socket_context_t {
    struct us_loop_t *loop;
    unsigned short timestamp;
    struct us_socket_t *head;
    struct us_socket_t *iterator;
    struct us_socket_context_t *prev, *next;
    struct us_socket_t *(*on_open)(struct us_socket_t *, int is_client, char *ip, int ip_length);
    struct us_socket_t *(*on_data)(struct us_socket_t *, char *data, int length);
    struct us_socket_t *(*on_writable)(struct us_socket_t *);
    struct us_socket_t *(*on_close)(struct us_socket_t *, int code, void *reason);
    struct us_socket_t *(*on_socket_timeout)(struct us_socket_t *);
    struct us_socket_t *(*on_end)(struct us_socket_t *);
    struct us_socket_t *(*on_connect_error)(struct us_socket_t *, int code);
    int (*is_low_prio)(struct us_socket_t *);
};

struct us_poll_t {
    struct {
        signed int fd : 28;
        unsigned int poll_type : 4;
    } state;
};


struct us_socket_t {
    struct us_poll_t p;
    struct us_socket_context_t *context;
    struct us_socket_t *prev, *next;
    unsigned short timeout : 14;
    unsigned short low_prio_state : 2;
};

struct us_listen_socket_t {
    struct us_socket_t s;
    unsigned int socket_ext_size;
};
void us_listen_socket_close(int ssl, struct us_listen_socket_t *ls);
int us_socket_local_port(int ssl, struct us_listen_socket_t *ls);
struct us_loop_t *uws_get_loop();
struct us_loop_t *uws_get_loop_with_native(void* existing_native_loop);
typedef enum
{
    _COMPRESSOR_MASK = 0x00FF,
    _DECOMPRESSOR_MASK = 0x0F00,
    DISABLED = 0,
    SHARED_COMPRESSOR = 1,
    SHARED_DECOMPRESSOR = 1 << 8,
    DEDICATED_DECOMPRESSOR_32KB = 15 << 8,
    DEDICATED_DECOMPRESSOR_16KB = 14 << 8,
    DEDICATED_DECOMPRESSOR_8KB = 13 << 8,
    DEDICATED_DECOMPRESSOR_4KB = 12 << 8,
    DEDICATED_DECOMPRESSOR_2KB = 11 << 8,
    DEDICATED_DECOMPRESSOR_1KB = 10 << 8,
    DEDICATED_DECOMPRESSOR_512B = 9 << 8,
    DEDICATED_DECOMPRESSOR = 15 << 8,
    DEDICATED_COMPRESSOR_3KB = 9 << 4 | 1,
    DEDICATED_COMPRESSOR_4KB = 9 << 4 | 2,
    DEDICATED_COMPRESSOR_8KB = 10 << 4 | 3,
    DEDICATED_COMPRESSOR_16KB = 11 << 4 | 4,
    DEDICATED_COMPRESSOR_32KB = 12 << 4 | 5,
    DEDICATED_COMPRESSOR_64KB = 13 << 4 | 6,
    DEDICATED_COMPRESSOR_128KB = 14 << 4 | 7,
    DEDICATED_COMPRESSOR_256KB = 15 << 4 | 8,
    DEDICATED_COMPRESSOR = 15 << 4 | 8
} uws_compress_options_t;

typedef enum
{
    CONTINUATION = 0,
    TEXT = 1,
    BINARY = 2,
    CLOSE = 8,
    PING = 9,
    PONG = 10
} uws_opcode_t;

typedef enum
{
    BACKPRESSURE,
    SUCCESS,
    DROPPED
} uws_sendstatus_t;

typedef struct
{
    int port;
    const char *host;
    int options;
} uws_app_listen_config_t;

struct uws_app_s;
struct uws_req_s;
struct uws_res_s;
struct uws_websocket_s;
struct uws_header_iterator_s;
typedef struct uws_app_s uws_app_t;
typedef struct uws_req_s uws_req_t;
typedef struct uws_res_s uws_res_t;
typedef struct uws_socket_context_s uws_socket_context_t;
typedef struct uws_websocket_s uws_websocket_t;

typedef void (*uws_websocket_handler)(uws_websocket_t *ws, void* user_data);
typedef void (*uws_websocket_message_handler)(uws_websocket_t *ws, const char *message, size_t length, uws_opcode_t opcode, void* user_data);
typedef void (*uws_websocket_ping_pong_handler)(uws_websocket_t *ws, const char *message, size_t length, void* user_data);
typedef void (*uws_websocket_close_handler)(uws_websocket_t *ws, int code, const char *message, size_t length, void* user_data);
typedef void (*uws_websocket_upgrade_handler)(uws_res_t *response, uws_req_t *request, uws_socket_context_t *context, void* user_data);
typedef struct
{
    uws_compress_options_t compression;
    unsigned int maxPayloadLength;
    unsigned short idleTimeout;
    unsigned int maxBackpressure;
    bool closeOnBackpressureLimit;
    bool resetIdleTimeoutOnSend;
    bool sendPingsAutomatically;
    unsigned short maxLifetime;
    uws_websocket_upgrade_handler upgrade;
    uws_websocket_handler open;
    uws_websocket_message_handler message;
    uws_websocket_handler drain;
    uws_websocket_ping_pong_handler ping;
    uws_websocket_ping_pong_handler pong;
    uws_websocket_close_handler close;
} uws_socket_behavior_t;

typedef struct {
    bool ok;
    bool has_responded;
} uws_try_end_result_t;

typedef void (*uws_listen_handler)(struct us_listen_socket_t *listen_socket, uws_app_listen_config_t config, void *user_data);
typedef void (*uws_method_handler)(uws_res_t *response, uws_req_t *request, void *user_data);
typedef void (*uws_filter_handler)(uws_res_t *response, int, void *user_data);
typedef void (*uws_missing_server_handler)(const char *hostname, size_t hostname_length, void *user_data);
typedef void (*uws_get_headers_server_handler)(const char *header_name, size_t header_name_size, const char *header_value, size_t header_value_size, void *user_data);


uws_app_t *uws_create_app(int ssl, struct us_socket_context_options_t options);
void uws_app_destroy(int ssl, uws_app_t *app);
void uws_app_get(int ssl, uws_app_t *app, const char *pattern, uws_method_handler handler, void *user_data);
void uws_app_post(int ssl, uws_app_t *app, const char *pattern, uws_method_handler handler, void *user_data);
void uws_app_options(int ssl, uws_app_t *app, const char *pattern, uws_method_handler handler, void *user_data);
void uws_app_delete(int ssl, uws_app_t *app, const char *pattern, uws_method_handler handler, void *user_data);
void uws_app_patch(int ssl, uws_app_t *app, const char *pattern, uws_method_handler handler, void *user_data);
void uws_app_put(int ssl, uws_app_t *app, const char *pattern, uws_method_handler handler, void *user_data);
void uws_app_head(int ssl, uws_app_t *app, const char *pattern, uws_method_handler handler, void *user_data);
void uws_app_connect(int ssl, uws_app_t *app, const char *pattern, uws_method_handler handler, void *user_data);
void uws_app_trace(int ssl, uws_app_t *app, const char *pattern, uws_method_handler handler, void *user_data);
void uws_app_any(int ssl, uws_app_t *app, const char *pattern, uws_method_handler handler, void *user_data);

void uws_app_run(int ssl, uws_app_t *);

void uws_app_listen(int ssl, uws_app_t *app, int port, uws_listen_handler handler, void *user_data);
void uws_app_listen_with_config(int ssl, uws_app_t *app, uws_app_listen_config_t config, uws_listen_handler handler, void *user_data);
bool uws_constructor_failed(int ssl, uws_app_t *app);
unsigned int uws_num_subscribers(int ssl, uws_app_t *app, const char *topic, size_t topic_length);
bool uws_publish(int ssl, uws_app_t *app, const char *topic, size_t topic_length, const char *message, size_t message_length, uws_opcode_t opcode, bool compress);
void *uws_get_native_handle(int ssl, uws_app_t *app);
void uws_remove_server_name(int ssl, uws_app_t *app, const char *hostname_pattern, size_t hostname_pattern_length);
void uws_add_server_name(int ssl, uws_app_t *app, const char *hostname_pattern, size_t hostname_pattern_length);
void uws_add_server_name_with_options(int ssl, uws_app_t *app, const char *hostname_pattern, size_t hostname_pattern_length, struct us_socket_context_options_t options);
void uws_missing_server_name(int ssl, uws_app_t *app, uws_missing_server_handler handler, void *user_data);
void uws_filter(int ssl, uws_app_t *app, uws_filter_handler handler, void *user_data);


void uws_res_end(int ssl, uws_res_t *res, const char *data, size_t length, bool close_connection);
void uws_res_pause(int ssl, uws_res_t *res);
void uws_res_resume(int ssl, uws_res_t *res);
void uws_res_write_continue(int ssl, uws_res_t *res);
void uws_res_write_status(int ssl, uws_res_t *res, const char *status, size_t length);
void uws_res_write_header(int ssl, uws_res_t *res, const char *key, size_t key_length, const char *value, size_t value_length);
void uws_res_override_write_offset(int ssl, uws_res_t *res, uintmax_t offset);

void uws_res_write_header_int(int ssl, uws_res_t *res, const char *key, size_t key_length, uint64_t value);
void uws_res_end_without_body(int ssl, uws_res_t *res, bool close_connection);
bool uws_res_write(int ssl, uws_res_t *res, const char *data, size_t length);
uintmax_t uws_res_get_write_offset(int ssl, uws_res_t *res);
void *uws_res_get_native_handle(int ssl, uws_res_t *res);
bool uws_res_has_responded(int ssl, uws_res_t *res);
void uws_res_on_writable(int ssl, uws_res_t *res, bool (*handler)(uws_res_t *res, uintmax_t, void *opcional_data), void *user_data);
void uws_res_on_aborted(int ssl, uws_res_t *res, void (*handler)(uws_res_t *res, void *opcional_data), void *opcional_data);
void uws_res_on_data(int ssl, uws_res_t *res, void (*handler)(uws_res_t *res, const char *chunk, size_t chunk_length, bool is_end, void *opcional_data), void *opcional_data);
void uws_res_upgrade(int ssl, uws_res_t *res, void *data, const char *sec_web_socket_key, size_t sec_web_socket_key_length, const char *sec_web_socket_protocol, size_t sec_web_socket_protocol_length, const char *sec_web_socket_extensions, size_t sec_web_socket_extensions_length, uws_socket_context_t *ws);
uws_try_end_result_t uws_res_try_end(int ssl, uws_res_t *res, const char *data, size_t length, uintmax_t total_size, bool close_connection);
void uws_res_cork(int ssl, uws_res_t *res,void(*callback)(uws_res_t *res, void* user_data) ,void* user_data);
size_t uws_res_get_remote_address(int ssl, uws_res_t *res, const char **dest);
size_t uws_res_get_remote_address_as_text(int ssl, uws_res_t *res, const char **dest);
size_t uws_res_get_proxied_remote_address(int ssl, uws_res_t *res, const char **dest);
size_t uws_res_get_proxied_remote_address_as_text(int ssl, uws_res_t *res, const char **dest);

bool uws_req_is_ancient(uws_req_t *res);
bool uws_req_get_yield(uws_req_t *res);
void uws_req_set_field(uws_req_t *res, bool yield);
size_t uws_req_get_url(uws_req_t *res, const char **dest);
size_t uws_req_get_method(uws_req_t *res, const char **dest);
size_t uws_req_get_case_sensitive_method(uws_req_t *res, const char **dest);

size_t uws_req_get_header(uws_req_t *res, const char *lower_case_header, size_t lower_case_header_length, const char **dest);
size_t uws_req_get_query(uws_req_t *res, const char *key, size_t key_length, const char **dest);
size_t uws_req_get_parameter(uws_req_t *res, unsigned short index, const char **dest);
size_t uws_req_get_full_url(uws_req_t *res, const char **dest);
void uws_req_for_each_header(uws_req_t *res, uws_get_headers_server_handler handler, void *user_data);

void uws_ws(int ssl, uws_app_t *app, const char *pattern, uws_socket_behavior_t behavior, void* user_data);
void *uws_ws_get_user_data(int ssl, uws_websocket_t *ws);
void uws_ws_close(int ssl, uws_websocket_t *ws);
uws_sendstatus_t uws_ws_send(int ssl, uws_websocket_t *ws, const char *message, size_t length, uws_opcode_t opcode);
uws_sendstatus_t uws_ws_send_with_options(int ssl, uws_websocket_t *ws, const char *message, size_t length, uws_opcode_t opcode, bool compress, bool fin);
uws_sendstatus_t uws_ws_send_fragment(int ssl, uws_websocket_t *ws, const char *message, size_t length, bool compress);
uws_sendstatus_t uws_ws_send_first_fragment(int ssl, uws_websocket_t *ws, const char *message, size_t length, bool compress);
uws_sendstatus_t uws_ws_send_first_fragment_with_opcode(int ssl, uws_websocket_t *ws, const char *message, size_t length, uws_opcode_t opcode, bool compress);
uws_sendstatus_t uws_ws_send_last_fragment(int ssl, uws_websocket_t *ws, const char *message, size_t length, bool compress);
void uws_ws_end(int ssl, uws_websocket_t *ws, int code, const char *message, size_t length);
void uws_ws_cork(int ssl, uws_websocket_t *ws, void (*handler)(void *user_data), void *user_data);

bool uws_ws_subscribe(int ssl, uws_websocket_t *ws, const char *topic, size_t length);
bool uws_ws_unsubscribe(int ssl, uws_websocket_t *ws, const char *topic, size_t length);
bool uws_ws_is_subscribed(int ssl, uws_websocket_t *ws, const char *topic, size_t length);
void uws_ws_iterate_topics(int ssl, uws_websocket_t *ws, void (*callback)(const char *topic, size_t length, void *user_data), void *user_data);
bool uws_ws_publish(int ssl, uws_websocket_t *ws, const char *topic, size_t topic_length, const char *message, size_t message_length);
bool uws_ws_publish_with_options(int ssl, uws_websocket_t *ws, const char *topic, size_t topic_length, const char *message, size_t message_length, uws_opcode_t opcode, bool compress);
int uws_ws_get_buffered_amount(int ssl, uws_websocket_t *ws);
size_t uws_ws_get_remote_address(int ssl, uws_websocket_t *ws, const char **dest);
size_t uws_ws_get_remote_address_as_text(int ssl, uws_websocket_t *ws, const char **dest);
"""
)

library_extension = "dll" if platform.system().lower() == "windows" else "so"
library_path = os.path.join(
    os.path.dirname(__file__),
    "libsocketify_%s_%s.%s"
    % (
        platform.system().lower(),
        "arm64" if "arm" in platform.processor().lower() else "amd64",
        library_extension,
    ),
)


lib = ffi.dlopen(library_path)


@ffi.callback("void(const char*, size_t, void*)")
def uws_missing_server_name(hostname, hostname_length, user_data):
    if not user_data == ffi.NULL:
        try:
            app = ffi.from_handle(user_data)
            if hostname == ffi.NULL:
                data = None
            else:
                data = ffi.unpack(hostname, hostname_length).decode("utf-8")

            handler = app._missing_server_handler
            if inspect.iscoroutinefunction(handler):
                app.run_async(handler(data))
            else:
                handler(data)
        except Exception as err:
            print(
                "Uncaught Exception: %s" % str(err)
            )  # just log in console the error to call attention


@ffi.callback("void(uws_websocket_t*, void*)")
def uws_websocket_factory_drain_handler(ws, user_data):
    if not user_data == ffi.NULL:
        (handlers, app) = ffi.from_handle(user_data)
        instances = app._ws_factory.get(app, ws)
        (ws, dispose) = instances
        try:
            handler = handlers.drain
            if inspect.iscoroutinefunction(handler):
                future = app.run_async(handler(ws))
                if dispose:
                    def when_finished(_):
                        app._ws_factory.dispose(instances)

                    future.add_done_callback(when_finished)
            else:
                handler(ws)
                if dispose:
                    app._ws_factory.dispose(instances)
        except Exception as err:
            if dispose:
                    app._ws_factory.dispose(instances)
            print(
                "Uncaught Exception: %s" % str(err)
            )  # just log in console the error to call attention

@ffi.callback("void(uws_websocket_t*, void*)")
def uws_websocket_drain_handler(ws, user_data):
    if not user_data == ffi.NULL:
        try:
            (handlers, app) = ffi.from_handle(user_data)
            ws = WebSocket(ws, app.SSL, app.loop)
            handler = handlers.drain
            if inspect.iscoroutinefunction(handler):
                app.run_async(handler(ws))
            else:
                handler(ws)
        except Exception as err:
            print(
                "Uncaught Exception: %s" % str(err)
            )  # just log in console the error to call attention


@ffi.callback("void(uws_websocket_t*, void*)")
def uws_websocket_factory_open_handler(ws, user_data):
    if not user_data == ffi.NULL:
        (handlers, app) = ffi.from_handle(user_data)
        instances = app._ws_factory.get(app, ws)
        (ws, dispose) = instances
        try:
            handler = handlers.open
            if inspect.iscoroutinefunction(handler):
                future = app.run_async(handler(ws))
                if dispose:
                    def when_finished(_):
                        app._ws_factory.dispose(instances)

                    future.add_done_callback(when_finished)
            else:
                handler(ws)
                if dispose:
                    app._ws_factory.dispose(instances)
        except Exception as err:
            if dispose:
                    app._ws_factory.dispose(instances)
            print(
                "Uncaught Exception: %s" % str(err)
            )  # just log in console the error to call attention

@ffi.callback("void(uws_websocket_t*, void*)")
def uws_websocket_open_handler(ws, user_data):

    if not user_data == ffi.NULL:
        try:
            (handlers, app) = ffi.from_handle(user_data)
            ws = WebSocket(ws, app.SSL, app.loop)
            handler = handlers.open
            if inspect.iscoroutinefunction(handler):
                app.run_async(handler(ws))
            else:
                handler(ws)
        except Exception as err:
            print(
                "Uncaught Exception: %s" % str(err)
            )  # just log in console the error to call attention


@ffi.callback("void(uws_websocket_t*, const char*, size_t, uws_opcode_t, void*)")
def uws_websocket_factory_message_handler(ws, message, length, opcode, user_data):
    if not user_data == ffi.NULL:
        (handlers, app) = ffi.from_handle(user_data)
        instances = app._ws_factory.get(app, ws)
        (ws, dispose) = instances
        try:
            if message == ffi.NULL:
                data = None
            else:
                data = ffi.unpack(message, length)
            opcode = OpCode(opcode)
            if opcode == OpCode.TEXT:
                data = data.decode("utf-8")

            handler = handlers.message
            if inspect.iscoroutinefunction(handler):
                future = app.run_async(handler(ws, data, opcode))
                if dispose:
                    def when_finished(_):
                        app._ws_factory.dispose(instances)

                    future.add_done_callback(when_finished)
            else:
                handler(ws, data, opcode)
                if dispose:
                    app._ws_factory.dispose(instances)

        except Exception as err:
            if dispose:
               app._ws_factory.dispose(instances)
            print(
                "Uncaught Exception: %s" % str(err)
            )  # just log in console the error to call attention

@ffi.callback("void(uws_websocket_t*, const char*, size_t, uws_opcode_t, void*)")
def uws_websocket_message_handler(ws, message, length, opcode, user_data):
    if not user_data == ffi.NULL:
        try:
            (handlers, app) = ffi.from_handle(user_data)
            ws = WebSocket(ws, app.SSL, app.loop)

            if message == ffi.NULL:
                data = None
            else:
                data = ffi.unpack(message, length)
            opcode = OpCode(opcode)
            if opcode == OpCode.TEXT:
                data = data.decode("utf-8")

            handler = handlers.message
            if inspect.iscoroutinefunction(handler):
                app.run_async(handler(ws, data, opcode))
            else:
                handler(ws, data, opcode)

        except Exception as err:
            print(
                "Uncaught Exception: %s" % str(err)
            )  # just log in console the error to call attention


@ffi.callback("void(uws_websocket_t*, const char*, size_t, void*)")
def uws_websocket_factory_pong_handler(ws, message, length, user_data):
    if not user_data == ffi.NULL:
        (handlers, app) = ffi.from_handle(user_data)
        instances = app._ws_factory.get(app, ws)
        (ws, dispose) = instances
        try:
            if message == ffi.NULL:
                data = None
            else:
                data = ffi.unpack(message, length)

            handler = handlers.pong
            if inspect.iscoroutinefunction(handler):
                future = app.run_async(handler(ws, data))
                if dispose:
                    def when_finished(_):
                        app._ws_factory.dispose(instances)

                    future.add_done_callback(when_finished)
            else:
                handler(ws, data)
                if dispose:
                    app._ws_factory.dispose(instances)

        except Exception as err:
            if dispose:
               app._ws_factory.dispose(instances)
            print(
                "Uncaught Exception: %s" % str(err)
            )  # just log in console the error to call attention
@ffi.callback("void(uws_websocket_t*, const char*, size_t, void*)")
def uws_websocket_pong_handler(ws, message, length, user_data):
    if not user_data == ffi.NULL:
        try:
            (handlers, app) = ffi.from_handle(user_data)
            ws = WebSocket(ws, app.SSL, app.loop)
            if message == ffi.NULL:
                data = None
            else:
                data = ffi.unpack(message, length)

            handler = handlers.pong
            if inspect.iscoroutinefunction(handler):
                app.run_async(handler(ws, data))
            else:
                handler(ws, data)
        except Exception as err:
            print(
                "Uncaught Exception: %s" % str(err)
            )  # just log in console the error to call attention


@ffi.callback("void(uws_websocket_t*, const char*, size_t, void*)")
def uws_websocket_factory_ping_handler(ws, message, length, user_data):
    if not user_data == ffi.NULL:
        (handlers, app) = ffi.from_handle(user_data)
        instances = app._ws_factory.get(app, ws)
        (ws, dispose) = instances

        try:
            if message == ffi.NULL:
                data = None
            else:
                data = ffi.unpack(message, length)

            handler = handlers.ping
            if inspect.iscoroutinefunction(handler):
                future = app.run_async(handler(ws, data))
                if dispose:
                    def when_finished(_):
                        app._ws_factory.dispose(instances)

                    future.add_done_callback(when_finished)
            else:
                handler(ws, data)
                if dispose:
                    app._ws_factory.dispose(instances)

        except Exception as err:
            if dispose:
               app._ws_factory.dispose(instances)
            print(
                "Uncaught Exception: %s" % str(err)
            )  # just log in console the error to call attention

@ffi.callback("void(uws_websocket_t*, const char*, size_t, void*)")
def uws_websocket_ping_handler(ws, message, length, user_data):
    if not user_data == ffi.NULL:
        try:
            (handlers, app) = ffi.from_handle(user_data)
            ws = WebSocket(ws, app.SSL, app.loop)

            if message == ffi.NULL:
                data = None
            else:
                data = ffi.unpack(message, length)

            handler = handlers.ping
            if inspect.iscoroutinefunction(handler):
                app.run_async(handler(ws, data))
            else:
                handler(ws, data)

        except Exception as err:
            print(
                "Uncaught Exception: %s" % str(err)
            )  # just log in console the error to call attention


@ffi.callback("void(uws_websocket_t*, int, const char*, size_t, void*)")
def uws_websocket_factory_close_handler(ws, code, message, length, user_data):
    if not user_data == ffi.NULL:
        (handlers, app) = ffi.from_handle(user_data)
        instances = app._ws_factory.get(app, ws)
        (ws, dispose) = instances

        try:
            if message == ffi.NULL:
                data = None
            else:
                data = ffi.unpack(message, length)

            handler = handlers.close

            if handler is None:
                if dispose:
                    app._ws_factory.dispose(instances)
                return

            if inspect.iscoroutinefunction(handler):
                future = app.run_async(handler(ws, int(code), data))

                def when_finished(_):
                    key = ws.get_user_data_uuid()
                    if not key is None:
                        SocketRefs.pop(key, None)
                    if dispose:
                        app._ws_factory.dispose(instances)

                future.add_done_callback(when_finished)
            else:
                handler(ws, int(code), data)
                key = ws.get_user_data_uuid()
                if not key is None:
                    SocketRefs.pop(key, None)
                if dispose:
                    app._ws_factory.dispose(instances)

        except Exception as err:
            print(
                "Uncaught Exception: %s" % str(err)
            )  # just log in console the error to call attention

@ffi.callback("void(uws_websocket_t*, int, const char*, size_t, void*)")
def uws_websocket_close_handler(ws, code, message, length, user_data):
    if not user_data == ffi.NULL:
        try:
            (handlers, app) = ffi.from_handle(user_data)
            # pass to free data on WebSocket if needed
            ws = WebSocket(ws, app.SSL, app.loop)

            if message == ffi.NULL:
                data = None
            else:
                data = ffi.unpack(message, length)

            handler = handlers.close

            if handler is None:
                return

            if inspect.iscoroutinefunction(handler):
                future = app.run_async(handler(ws, int(code), data))

                def when_finished(_):
                    key = ws.get_user_data_uuid()
                    if not key is None:
                        SocketRefs.pop(key, None)

                future.add_done_callback(when_finished)
            else:
                handler(ws, int(code), data)
                key = ws.get_user_data_uuid()
                if not key is None:
                    SocketRefs.pop(key, None)

        except Exception as err:
            print(
                "Uncaught Exception: %s" % str(err)
            )  # just log in console the error to call attention


@ffi.callback("void(uws_res_t*, uws_req_t*, void*)")
def uws_generic_factory_method_handler(res, req, user_data):
    if not user_data == ffi.NULL:
        (handler, app) = ffi.from_handle(user_data)
        instances = app._factory.get(app, res, req)
        (response, request, dispose) = instances
        try:
            if inspect.iscoroutinefunction(handler):
                response.grab_aborted_handler()
                future = response.run_async(handler(response, request))
                if dispose:
                    def when_finished(_):
                        app._factory.dispose(instances)

                    future.add_done_callback(when_finished)
            else:
                handler(response, request)
                if dispose:
                    app._factory.dispose(instances)

        except Exception as err:
            response.grab_aborted_handler()
            app.trigger_error(err, response, request)
            if dispose:
                app._factory.dispose(instances)

@ffi.callback("void(uws_res_t*, uws_req_t*, uws_socket_context_t*, void*)")
def uws_websocket_factory_upgrade_handler(res, req, context, user_data):
    if not user_data == ffi.NULL:
        (handlers, app) = ffi.from_handle(user_data)
        instances = app._factory.get(app, res, req)
        (response, request, dispose) = instances
        try:
            handler = handlers.upgrade
       
            if inspect.iscoroutinefunction(handler):
                future = response.run_async(handler(response, request, context))
                if dispose:
                    def when_finished(_):
                        app._factory.dispose(instances)

                    future.add_done_callback(when_finished)
            else:
                handler(response, request, context)
                if dispose:
                    app._factory.dispose(instances)
        except Exception as err:
            response.grab_aborted_handler()
            app.trigger_error(err, response, request)
            if dispose:
                app._factory.dispose(instances)

@ffi.callback("void(uws_res_t*, uws_req_t*, uws_socket_context_t*, void*)")
def uws_websocket_upgrade_handler(res, req, context, user_data):
    if not user_data == ffi.NULL:
        (handlers, app) = ffi.from_handle(user_data)
        response = AppResponse(res, app.loop, app.SSL, app._template)
        request = AppRequest(req)
        try:
            handler = handlers.upgrade
            if inspect.iscoroutinefunction(handler):
                response.run_async(handler(response, request, context))
            else:
                handler(response, request, context)

        except Exception as err:
            response.grab_aborted_handler()
            app.trigger_error(err, response, request)


@ffi.callback("void(const char*, size_t, void*)")
def uws_req_for_each_topic_handler(topic, topic_size, user_data):
    if not user_data == ffi.NULL:
        try:
            ws = ffi.from_handle(user_data)
            header_name = ffi.unpack(topic, topic_size).decode("utf-8")
            ws.trigger_for_each_topic_handler(header_name, header_value)
        except Exception:  # invalid utf-8
            return


@ffi.callback("void(const char*, size_t, const char*, size_t, void*)")
def uws_req_for_each_header_handler(
    header_name, header_name_size, header_value, header_value_size, user_data
):
    if not user_data == ffi.NULL:
        try:
            req = ffi.from_handle(user_data)
            header_name = ffi.unpack(header_name, header_name_size).decode("utf-8")
            header_value = ffi.unpack(header_value, header_value_size).decode("utf-8")

            req.trigger_for_each_header_handler(header_name, header_value)
        except Exception:  # invalid utf-8
            return


@ffi.callback("void(uws_res_t*, uws_req_t*, void*)")
def uws_generic_factory_method_handler(res, req, user_data):
    if not user_data == ffi.NULL:
        (handler, app) = ffi.from_handle(user_data)
        instances = app._factory.get(app, res, req)
        (response, request, dispose) = instances
        try:
            if inspect.iscoroutinefunction(handler):
                response.grab_aborted_handler()
                future = response.run_async(handler(response, request))
                if dispose:
                    def when_finished(_):
                        app._factory.dispose(instances)

                    future.add_done_callback(when_finished)
            else:
                handler(response, request)
                if dispose:
                    app._factory.dispose(instances)

        except Exception as err:
            response.grab_aborted_handler()
            app.trigger_error(err, response, request)
            if dispose:
                app._factory.dispose(instances)
            
@ffi.callback("void(uws_res_t*, uws_req_t*, void*)")
def uws_generic_method_handler(res, req, user_data):
    if not user_data == ffi.NULL:
        (handler, app) = ffi.from_handle(user_data)
        response = AppResponse(res, app.loop, app.SSL, app._template)
        request = AppRequest(req)
            
        try:
            if inspect.iscoroutinefunction(handler):
                response.grab_aborted_handler()
                response.run_async(handler(response, request))
            else:
                handler(response, request)
        except Exception as err:
            response.grab_aborted_handler()
            app.trigger_error(err, response, request)


@ffi.callback("void(struct us_listen_socket_t*, uws_app_listen_config_t, void*)")
def uws_generic_listen_handler(listen_socket, config, user_data):
    if listen_socket == ffi.NULL:
        raise RuntimeError("Failed to listen on port %d" % int(config.port))

    if not user_data == ffi.NULL:
        app = ffi.from_handle(user_data)
        config.port = lib.us_socket_local_port(app.SSL, listen_socket)
        if hasattr(app, "_listen_handler") and hasattr(app._listen_handler, "__call__"):
            app.socket = listen_socket
            app._listen_handler(
                None
                if config == ffi.NULL
                else AppListenOptions(
                    port=int(config.port),
                    host=None
                    if config.host == ffi.NULL
                    else ffi.string(config.host).decode("utf-8"),
                    options=int(config.options),
                )
            )


@ffi.callback("void(uws_res_t*, void*)")
def uws_generic_aborted_handler(response, user_data):
    if not user_data == ffi.NULL:
        try:
            res = ffi.from_handle(user_data)
            res.trigger_aborted()
        except:
            pass


@ffi.callback("void(uws_res_t*, const char*, size_t, bool, void*)")
def uws_generic_on_data_handler(res, chunk, chunk_length, is_end, user_data):
    if not user_data == ffi.NULL:
        res = ffi.from_handle(user_data)
        if chunk == ffi.NULL:
            data = None
        else:
            data = ffi.unpack(chunk, chunk_length)

        res.trigger_data_handler(data, bool(is_end))


@ffi.callback("bool(uws_res_t*, uintmax_t, void*)")
def uws_generic_on_writable_handler(res, offset, user_data):
    if not user_data == ffi.NULL:
        res = ffi.from_handle(user_data)
        result = res.trigger_writable_handler(offset)
        return result
    return False


@ffi.callback("void(uws_res_t*, void*)")
def uws_generic_cork_handler(res, user_data):
    if not user_data == ffi.NULL:
        response = ffi.from_handle(user_data)
        try:
            if inspect.iscoroutinefunction(response._cork_handler):
                raise RuntimeError("Calls inside cork must be sync")
            response._cork_handler(response)
        except Exception as err:
            print("Error on cork handler %s" % str(err))


@ffi.callback("void(void*)")
def uws_ws_cork_handler(user_data):
    if not user_data == ffi.NULL:
        ws = ffi.from_handle(user_data)
        try:
            if inspect.iscoroutinefunction(ws._cork_handler):
                raise RuntimeError("Calls inside cork must be sync")
            ws._cork_handler(ws)
        except Exception as err:
            print("Error on cork handler %s" % str(err))


# Compressor mode is 8 lowest bits where HIGH4(windowBits), LOW4(memLevel).
# Decompressor mode is 8 highest bits LOW4(windowBits).
# If compressor or decompressor bits are 1, then they are shared.
# If everything is just simply 0, then everything is disabled.
class CompressOptions(IntEnum):
    # Disabled, shared, shared are "special" values
    DISABLED = lib.DISABLED
    SHARED_COMPRESSOR = lib.SHARED_COMPRESSOR
    SHARED_DECOMPRESSOR = lib.SHARED_DECOMPRESSOR
    # Highest 4 bits describe decompressor
    DEDICATED_DECOMPRESSOR_32KB = lib.DEDICATED_DECOMPRESSOR_32KB
    DEDICATED_DECOMPRESSOR_16KB = lib.DEDICATED_DECOMPRESSOR_16KB
    DEDICATED_DECOMPRESSOR_8KB = lib.DEDICATED_DECOMPRESSOR_8KB
    DEDICATED_DECOMPRESSOR_4KB = lib.DEDICATED_DECOMPRESSOR_4KB
    DEDICATED_DECOMPRESSOR_2KB = lib.DEDICATED_DECOMPRESSOR_2KB
    DEDICATED_DECOMPRESSOR_1KB = lib.DEDICATED_DECOMPRESSOR_1KB
    DEDICATED_DECOMPRESSOR_512B = lib.DEDICATED_DECOMPRESSOR_512B
    # Same as 32kb
    DEDICATED_DECOMPRESSOR = (lib.DEDICATED_DECOMPRESSOR,)

    # Lowest 8 bit describe compressor
    DEDICATED_COMPRESSOR_3KB = lib.DEDICATED_COMPRESSOR_3KB
    DEDICATED_COMPRESSOR_4KB = lib.DEDICATED_COMPRESSOR_4KB
    DEDICATED_COMPRESSOR_8KB = lib.DEDICATED_COMPRESSOR_8KB
    DEDICATED_COMPRESSOR_16KB = lib.DEDICATED_COMPRESSOR_16KB
    DEDICATED_COMPRESSOR_32KB = lib.DEDICATED_COMPRESSOR_32KB
    DEDICATED_COMPRESSOR_64KB = lib.DEDICATED_COMPRESSOR_64KB
    DEDICATED_COMPRESSOR_128KB = lib.DEDICATED_COMPRESSOR_128KB
    DEDICATED_COMPRESSOR_256KB = lib.DEDICATED_COMPRESSOR_256KB
    # Same as 256kb
    DEDICATED_COMPRESSOR = lib.DEDICATED_COMPRESSOR


class OpCode(IntEnum):
    CONTINUATION = 0
    TEXT = 1
    BINARY = 2
    CLOSE = 8
    PING = 9
    PONG = 10


class SendStatus(IntEnum):
    BACKPRESSURE = 0
    SUCCESS = 1
    DROPPED = 2


# dict to keep socket data alive until closed if needed
SocketRefs = {}


class WebSocket:
    def __init__(self, websocket, ssl, loop):
        self.ws = websocket
        self.SSL = ssl
        self._ptr = ffi.new_handle(self)
        self.loop = loop
        self._cork_handler = None
        self._for_each_topic_handler = None
        self.socket_data_id = None
        self.socket_data = None
        self.got_socket_data = False

    def trigger_for_each_topic_handler(self, topic):
        if hasattr(self, "_for_each_topic_handler") and hasattr(
            self._for_each_topic_handler, "__call__"
        ):
            try:
                if inspect.iscoroutinefunction(self._for_each_topic_handler):
                    raise RuntimeError(
                        "WebSocket.for_each_topic_handler must be synchronous"
                    )
                self._for_each_topic_handler(topic)
            except Exception as err:
                print("Error on for each topic handler %s" % str(err))

    # uuid for socket data, used to free data after socket closes
    def get_user_data_uuid(self):
        try:
            if self.got_socket_data:
                return self.socket_data_id
            user_data = lib.uws_ws_get_user_data(self.SSL, self.ws)
            if user_data == ffi.NULL:
                return None
            (data, socket_data_id) = ffi.from_handle(user_data)
            self.socket_data_id = socket_data_id
            self.socket_data = data
            self.got_socket_data = True
            return socket_data_id
        except:
            return None

    def get_user_data(self):
        try:
            if self.got_socket_data:
                return self.socket_data
            user_data = lib.uws_ws_get_user_data(self.SSL, self.ws)
            if user_data == ffi.NULL:
                return None
            (data, socket_data_id) = ffi.from_handle(user_data)
            self.socket_data_id = socket_data_id
            self.socket_data = data
            self.got_socket_data = True
            return data
        except:
            return None

    def get_buffered_amount(self):
        return int(lib.uws_ws_get_buffered_amount(self.SSL, self.ws))

    def subscribe(self, topic):
        try:
            if isinstance(topic, str):
                data = topic.encode("utf-8")
            elif isinstance(topic, bytes):
                data = topic
            else:
                return False

            return bool(lib.uws_ws_subscribe(self.SSL, self.ws, data, len(data)))
        except:
            return False

    def unsubscribe(self, topic):
        try:
            if isinstance(topic, str):
                data = topic.encode("utf-8")
            elif isinstance(topic, bytes):
                data = topic
            else:
                return False

            return bool(lib.uws_ws_unsubscribe(self.SSL, self.ws, data, len(data)))
        except:
            return False

    def is_subscribed(self, topic):
        try:
            if isinstance(topic, str):
                data = topic.encode("utf-8")
            elif isinstance(topic, bytes):
                data = topic
            else:
                return False

            return bool(lib.uws_ws_is_subscribed(self.SSL, self.ws, data, len(data)))
        except:
            return False

    def publish(self, topic, message, opcode=OpCode.BINARY, compress=False):
        try:
            if isinstance(topic, str):
                topic_data = topic.encode("utf-8")
            elif isinstance(topic, bytes):
                topic_data = topic
            else:
                return False

            if isinstance(message, str):
                data = message.encode("utf-8")
            elif isinstance(message, bytes):
                data = message
            elif message == None:
                data = b""
            else:
                data = json.dumps(message).encode("utf-8")

            return bool(
                lib.uws_ws_publish_with_options(
                    self.SSL,
                    self.ws,
                    topic_data,
                    len(topic_data),
                    data,
                    len(data),
                    int(opcode),
                    bool(compress),
                )
            )
        except:
            return False

    def get_topics(self):
        topics = []

        def copy_topics(topic):
            topics.append(topic)

        self.for_each_topic(copy_topics)
        return topics

    def for_each_topic(self, handler):
        self._for_each_topic_handler = handler
        lib.uws_ws_iterate_topics(
            self.SSL, self.ws, uws_req_for_each_topic_handler, self._ptr
        )

    def get_remote_address_bytes(self):
        buffer = ffi.new("char**")
        length = lib.uws_ws_get_remote_address(self.SSL, self.ws, buffer)
        buffer_address = ffi.addressof(buffer, 0)[0]
        if buffer_address == ffi.NULL:
            return None
        try:
            return ffi.unpack(buffer_address, length)
        except Exception:  # invalid
            return None

    def get_remote_address(self):
        buffer = ffi.new("char**")
        length = lib.uws_ws_get_remote_address_as_text(self.SSL, self.ws, buffer)
        buffer_address = ffi.addressof(buffer, 0)[0]
        if buffer_address == ffi.NULL:
            return None
        try:
            return ffi.unpack(buffer_address, length).decode("utf-8")
        except Exception:  # invalid utf-8
            return None

    def send_fragment(self, message, compress=False):
        try:
            if isinstance(message, str):
                data = message.encode("utf-8")
            elif isinstance(message, bytes):
                data = message
            elif message == None:
                lib.uws_ws_send_fragment(self.SSL, self.ws, b"", 0, compress)
                return self
            else:
                data = json.dumps(message).encode("utf-8")

            return SendStatus(
                lib.uws_ws_send_fragment(self.SSL, self.ws, data, len(data), compress)
            )
        except:
            return None

    def send_last_fragment(self, message, compress=False):
        try:
            if isinstance(message, str):
                data = message.encode("utf-8")
            elif isinstance(message, bytes):
                data = message
            elif message == None:
                lib.uws_ws_send_last_fragment(self.SSL, self.ws, b"", 0, compress)
                return self
            else:
                data = json.dumps(message).encode("utf-8")

            return SendStatus(
                lib.uws_ws_send_last_fragment(
                    self.SSL, self.ws, data, len(data), compress
                )
            )
        except:
            return None

    def send_first_fragment(self, message, opcode=OpCode.BINARY, compress=False):
        try:
            if isinstance(message, str):
                data = message.encode("utf-8")
            elif isinstance(message, bytes):
                data = message
            elif message == None:
                lib.uws_ws_send_first_fragment_with_opcode(
                    self.SSL, self.ws, b"", 0, int(opcode), compress
                )
                return self
            else:
                data = json.dumps(message).encode("utf-8")

            return SendStatus(
                lib.uws_ws_send_first_fragment_with_opcode(
                    self.SSL, self.ws, data, len(data), int(opcode), compress
                )
            )
        except:
            return None

    def cork_send(self, message, opcode=OpCode.BINARY, compress=False, fin=True):
        self.cork(lambda ws: ws.send(message, opcode, compress, fin))
        return self

    def send(self, message, opcode=OpCode.BINARY, compress=False, fin=True):
        try:
            if isinstance(message, str):
                data = message.encode("utf-8")
            elif isinstance(message, bytes):
                data = message
            elif message == None:
                lib.uws_ws_send_with_options(
                    self.SSL, self.ws, b"", 0, int(opcode), compress, fin
                )
                return self
            else:
                data = json.dumps(message).encode("utf-8")

            return SendStatus(
                lib.uws_ws_send_with_options(
                    self.SSL, self.ws, data, len(data), int(opcode), compress, fin
                )
            )
        except:
            return None

    def cork_end(self, code=0, message=None):
        self.cork(lambda ws: ws.end(message, code, message))
        return self

    def end(self, code=0, message=None):
        try:
            if not isinstance(code, int):
                raise RuntimeError("code must be an int")
            if isinstance(message, str):
                data = message.encode("utf-8")
            elif isinstance(message, bytes):
                data = message
            elif message == None:
                lib.uws_ws_end(self.SSL, self.ws, b"", 0)
                return self
            else:
                data = json.dumps(message).encode("utf-8")

            lib.uws_ws_end(self.SSL, self.ws, code, data, len(data))
        finally:
            return self

    def close(self):
        lib.uws_ws_close(self.SSL, self._ptr)
        return self

    def cork(self, callback):
        self._cork_handler = callback
        lib.uws_ws_cork(self.SSL, self.ws, uws_ws_cork_handler, self._ptr)

    def __del__(self):
        self.ws = ffi.NULL
        self._ptr = ffi.NULL


class WSBehaviorHandlers:
    def __init__(self):
        self.upgrade = None
        self.open = None
        self.message = None
        self.drain = None
        self.ping = None
        self.pong = None
        self.close = None


class WebSocketFactory:
    def __init__(self, app, max_size):
        self.factory_queue = []        
        for _ in range(0, max_size):
            websocket = WebSocket(None, app.SSL, app.loop)
            self.factory_queue.append((websocket, True))
    def get(self, app, ws):
        if len(self.factory_queue) == 0:
            response = WebSocket(ws, app.SSL, app.loop)
            return (response, False)

        instances = self.factory_queue.pop()
        (websocket, _) = instances
        websocket.ws = ws
        return instances
    
    def dispose(self, instances):
        (websocket, _) = instances
        #dispose ws        
        websocket.ws = None
        websocket._cork_handler = None
        websocket._for_each_topic_handler = None
        websocket.socket_data_id = None
        websocket.socket_data = None
        websocket.got_socket_data = False
        self.factory_queue.append(instances)

class RequestResponseFactory:
    def __init__(self, app, max_size):
        self.factory_queue = []        
        for _ in range(0, max_size):
            response = AppResponse(None, app.loop, app.SSL, app._template)
            request =  AppRequest(None)
            self.factory_queue.append((response, request, True))

    def get(self, app, res, req):
        if len(self.factory_queue) == 0:
            response = AppResponse(res, app.loop, app.SSL, app._template)
            request =  AppRequest(req)
            return (response, request, False)

        instances = self.factory_queue.pop()
        (response, request, _) = instances
        response.res = res
        response._render = app._template
        request.req = req
        return instances

    def dispose(self, instances):
        (res, req, _) = instances
        #dispose res        
        res.res = None
        res.aborted = False
        res._aborted_handler = None
        res._writable_handler = None
        res._data_handler = None
        res._grabed_abort_handler_once = False
        res._write_jar = None
        res._cork_handler = None
        res._lastChunkOffset = 0
        res._chunkFuture = None
        res._dataFuture = None
        res._data = None
        res._render = None
        #dispose req
        req.req = None
        req.read_jar = None
        req.jar_parsed = False
        req._for_each_header_handler = None
        req._headers = None
        req._params = None
        req._query = None
        req._url = None
        req._full_url = None
        req._method = None
        self.factory_queue.append(instances)

class AppRequest:
    def __init__(self, request):
        self.req = request
        self.read_jar = None
        self.jar_parsed = False
        self._for_each_header_handler = None
        self._ptr = ffi.new_handle(self)
        self._headers = None
        self._params = None
        self._query = None
        self._url = None
        self._full_url = None
        self._method = None

    def get_cookie(self, name):
        if self.read_jar == None:
            if self.jar_parsed:
                return None

            if self._headers:
                raw_cookies = self._headers.get("cookie", None)
            else:
                raw_cookies = self.get_header("cookie")

            if raw_cookies:
                self.jar_parsed = True
                self.read_jar = cookies.SimpleCookie(raw_cookies)
            else:
                self.jar_parsed = True
                return None
        try:
            return self.read_jar[name].value
        except Exception:
            return None

    def get_url(self):
        if self._url:
            return self._url
        buffer = ffi.new("char**")
        length = lib.uws_req_get_url(self.req, buffer)
        buffer_address = ffi.addressof(buffer, 0)[0]
        if buffer_address == ffi.NULL:
            return None
        try:
            self._url = ffi.unpack(buffer_address, length).decode("utf-8")
            return self._url
        except Exception:  # invalid utf-8
            return None

    def get_full_url(self):
        if self._full_url:
            return self._full_url
        buffer = ffi.new("char**")
        length = lib.uws_req_get_full_url(self.req, buffer)
        buffer_address = ffi.addressof(buffer, 0)[0]
        if buffer_address == ffi.NULL:
            return None
        try:
            self._full_url = ffi.unpack(buffer_address, length).decode("utf-8")
            return self._full_url
        except Exception:  # invalid utf-8
            return None

    def get_method(self):
        if self._method:
            return self._method
        buffer = ffi.new("char**")
        # will use uws_req_get_case_sensitive_method until version v21 and switch back to uws_req_get_method for 0 impacts on behavior
        length = lib.uws_req_get_case_sensitive_method(self.req, buffer)
        buffer_address = ffi.addressof(buffer, 0)[0]
        if buffer_address == ffi.NULL:
            return None

        try:
            self._method = ffi.unpack(buffer_address, length).decode("utf-8")
            return self._method
        except Exception:  # invalid utf-8
            return None

    def for_each_header(self, handler):
        self._for_each_header_handler = handler
        lib.uws_req_for_each_header(
            self.req, uws_req_for_each_header_handler, self._ptr
        )

    def get_headers(self):
        if not self._headers is None:
            return self._headers

        self._headers = {}

        def copy_headers(key, value):
            self._headers[key] = value

        self.for_each_header(copy_headers)
        return self._headers

    def get_header(self, lower_case_header):
        if isinstance(lower_case_header, str):
            data = lower_case_header.encode("utf-8")
        elif isinstance(lower_case_header, bytes):
            data = lower_case_header
        else:
            data = json.dumps(lower_case_header).encode("utf-8")

        buffer = ffi.new("char**")
        length = lib.uws_req_get_header(self.req, data, len(data), buffer)
        buffer_address = ffi.addressof(buffer, 0)[0]
        if buffer_address == ffi.NULL:
            return None
        try:
            return ffi.unpack(buffer_address, length).decode("utf-8")
        except Exception:  # invalid utf-8
            return None

    def get_queries(self):
        try:
            if self._query:
                return self._query

            url = self.get_url()
            query = self.get_full_url()[len(url) :]
            if query.startswith("?"):
                query = query[1:]
            self._query = parse_qs(query, encoding="utf-8")
            return self._query
        except:
            self._query = {}
            return None

    def get_query(self, key):
        if self._query:
            return self._query.get(key, None)
        buffer = ffi.new("char**")

        if isinstance(key, str):
            key_data = key.encode("utf-8")
        elif isinstance(key, bytes):
            key_data = key
        else:
            key_data = json.dumps(key).encode("utf-8")

        length = lib.uws_req_get_query(self.req, key_data, len(key_data), buffer)
        buffer_address = ffi.addressof(buffer, 0)[0]
        if buffer_address == ffi.NULL:
            return None
        try:
            return ffi.unpack(buffer_address, length).decode("utf-8")
        except Exception:  # invalid utf-8
            return None

    def get_parameters(self):
        if self._params:
            return self._params
        self._params = []
        i = 0
        while True:
            value = self.get_parameter(i)
            if value:
                self._params.append(value)
            else:
                break
            i = i + 1
        return self._params

    def get_parameter(self, index):
        if self._params:
            try:
                return self._params[index]
            except:
                return None

        buffer = ffi.new("char**")
        length = lib.uws_req_get_parameter(
            self.req, ffi.cast("unsigned short", index), buffer
        )
        buffer_address = ffi.addressof(buffer, 0)[0]
        if buffer_address == ffi.NULL:
            return None
        try:
            return ffi.unpack(buffer_address, length).decode("utf-8")
        except Exception:  # invalid utf-8
            return None

    def preserve(self):
        # preserve queries, headers, parameters, method, url and full url
        self.get_queries()  # queries calls url and full_url so its preserved
        self.get_headers()
        self.get_parameters()
        self.get_method()
        return self

    def set_yield(self, has_yield):
        lib.uws_req_set_field(self.req, 1 if has_yield else 0)

    def get_yield(self):
        return bool(lib.uws_req_get_yield(self.req))

    def is_ancient(self):
        return bool(lib.uws_req_is_ancient(self.req))

    def trigger_for_each_header_handler(self, key, value):
        if hasattr(self, "_for_each_header_handler") and hasattr(
            self._for_each_header_handler, "__call__"
        ):
            try:
                if inspect.iscoroutinefunction(self._for_each_header_handler):
                    raise RuntimeError(
                        "AppResponse.for_each_header_handler must be synchronous"
                    )
                self._for_each_header_handler(key, value)
            except Exception as err:
                print("Error on data handler %s" % str(err))

        return self

    def __del__(self):
        self.req = ffi.NULL
        self._ptr = ffi.NULL


class AppResponse:
    def __init__(self, response, loop, ssl, render=None):
        self.res = response
        self.SSL = ssl
        self.aborted = False
        self.loop = loop
        self._aborted_handler = None
        self._writable_handler = None
        self._data_handler = None
        self._ptr = ffi.new_handle(self)
        self._grabed_abort_handler_once = False
        self._write_jar = None
        self._cork_handler = None
        self._lastChunkOffset = 0
        self._chunkFuture = None
        self._dataFuture = None
        self._data = None
        self._render = render

    def cork(self, callback):
        if not self.aborted:
            self.grab_aborted_handler()
            self._cork_handler = callback
            lib.uws_res_cork(self.SSL, self.res, uws_generic_cork_handler, self._ptr)

    def set_cookie(self, name, value, options={}):
        if self._write_jar == None:
            self._write_jar = cookies.SimpleCookie()
        self._write_jar[name] = quote_plus(value)
        if isinstance(options, dict):
            for key in options:
                if key == "expires" and isinstance(options[key], datetime):
                    self._write_jar[name][key] = options[key].strftime(
                        "%a, %d %b %Y %H:%M:%S GMT"
                    )
                else:
                    self._write_jar[name][key] = options[key]

    def trigger_aborted(self):
        self.aborted = True
        self._ptr = ffi.NULL
        self.res = ffi.NULL
        if hasattr(self, "_aborted_handler") and hasattr(
            self._aborted_handler, "__call__"
        ):
            try:
                if inspect.iscoroutinefunction(self._aborted_handler):
                    self.run_async(self._aborted_handler(self))
                else:
                    self._aborted_handler(self)
            except Exception as err:
                print("Error on abort handler %s" % str(err))
        return self

    def trigger_data_handler(self, data, is_end):
        if self.aborted:
            return self
        if hasattr(self, "_data_handler") and hasattr(self._data_handler, "__call__"):
            try:
                if inspect.iscoroutinefunction(self._data_handler):
                    self.run_async(self._data_handler(self, data, is_end))
                else:
                    self._data_handler(self, data, is_end)
            except Exception as err:
                print("Error on data handler %s" % str(err))

        return self

    def trigger_writable_handler(self, offset):
        if self.aborted:
            return False
        if hasattr(self, "_writable_handler") and hasattr(
            self._writable_handler, "__call__"
        ):
            try:
                if inspect.iscoroutinefunction(self._writable_handler):
                    raise RuntimeError("AppResponse.on_writable must be synchronous")
                return self._writable_handler(self, offset)
            except Exception as err:
                print("Error on writable handler %s" % str(err))
            return False
        return False

    def run_async(self, task):
        self.grab_aborted_handler()
        return self.loop.run_async(task, self)

    async def get_form_urlencoded(self, encoding="utf-8"):
        data = await self.get_data()
        try:
            # decode and unquote all
            result = {}
            parsed = parse_qs(b"".join(data), encoding=encoding)
            has_value = False
            for key in parsed:
                has_value = True
                try:
                    value = parsed[key]
                    new_key = key.decode(encoding)
                    last_value = value[len(value) - 1]

                    result[new_key] = unquote_plus(last_value.decode(encoding))
                except Exception as error:
                    pass
            return result if has_value else None
        except Exception as error:
            return None  # invalid encoding

    async def get_text(self, encoding="utf-8"):
        data = await self.get_data()
        try:
            return b"".join(data).decode(encoding)
        except Exception:
            return None  # invalid encoding

    async def get_json(self):
        data = await self.get_data()
        try:
            return json.loads(b"".join(data).decode("utf-8"))
        except Exception:
            return None  # invalid json

    def send_chunk(self, buffer, total_size):
        self._chunkFuture = self.loop.create_future()
        self._lastChunkOffset = 0

        def is_aborted(self):
            self.aborted = True
            try:
                if not self._chunkFuture.done():
                    self._chunkFuture.set_result(
                        (False, True)
                    )  # if aborted set to done True and ok False
            except:
                pass

        def on_writeble(self, offset):
            # Here the timeout is off, we can spend as much time before calling try_end we want to
            (ok, done) = self.try_end(
                buffer[offset - self._lastChunkOffset : :], total_size
            )
            if ok:
                self._chunkFuture.set_result((ok, done))
            return ok

        self.on_writable(on_writeble)
        self.on_aborted(is_aborted)

        if self.aborted:
            self._chunkFuture.set_result(
                (False, True)
            )  # if aborted set to done True and ok False
            return self._chunkFuture

        (ok, done) = self.try_end(buffer, total_size)
        if ok:
            self._chunkFuture.set_result((ok, done))
            return self._chunkFuture
        # failed to send chunk
        self._lastChunkOffset = self.get_write_offset()

        return self._chunkFuture

    def get_data(self):
        self._dataFuture = self.loop.create_future()
        self._data = []

        def is_aborted(self):
            self.aborted = True
            try:
                if not self._dataFuture.done():
                    self._dataFuture.set_result(self._data)
            except:
                pass

        def get_chunks(self, chunk, is_end):
            self._data.append(chunk)
            if is_end:
                self._dataFuture.set_result(self._data)
                self._data = None

        self.on_aborted(is_aborted)
        self.on_data(get_chunks)
        return self._dataFuture

    def grab_aborted_handler(self):
        # only needed if is async
        if not self.aborted and not self._grabed_abort_handler_once:
            self._grabed_abort_handler_once = True
            lib.uws_res_on_aborted(
                self.SSL, self.res, uws_generic_aborted_handler, self._ptr
            )
        return self

    def redirect(self, location, status_code=302):
        self.write_status(status_code)
        self.write_header("Location", location)
        self.end_without_body(False)
        return self

    def write_offset(self, offset):
        lib.uws_res_override_write_offset(
            self.SSL, self.res, ffi.cast("uintmax_t", offset)
        )
        return self

    def try_end(self, message, total_size, end_connection=False):
        try:
            if self.aborted:
                return (False, True)
            if self._write_jar != None:
                self.write_header("Set-Cookie", self._write_jar.output(header=""))
                self._write_jar = None
            if isinstance(message, str):
                data = message.encode("utf-8")
            elif isinstance(message, bytes):
                data = message
            else:
                return (False, True)
            result = lib.uws_res_try_end(
                self.SSL,
                self.res,
                data,
                len(data),
                ffi.cast("uintmax_t", total_size),
                1 if end_connection else 0,
            )
            return (bool(result.ok), bool(result.has_responded))
        except:
            return (False, True)

    def cork_end(self, message, end_connection=False):
        self.cork(lambda res: res.end(message, end_connection))
        return self

    def render(self, *args, **kwargs):
        if self._render:
            self.cork_end(self._render.render(*args, **kwargs))
            return self
        raise RuntimeError("No registered templated engine")

    def get_remote_address_bytes(self):
        buffer = ffi.new("char**")
        length = lib.uws_res_get_remote_address(self.SSL, self.res, buffer)
        buffer_address = ffi.addressof(buffer, 0)[0]
        if buffer_address == ffi.NULL:
            return None
        try:
            return ffi.unpack(buffer_address, length)
        except Exception:  # invalid
            return None

    def get_remote_address(self):
        buffer = ffi.new("char**")
        length = lib.uws_res_get_remote_address_as_text(self.SSL, self.res, buffer)
        buffer_address = ffi.addressof(buffer, 0)[0]
        if buffer_address == ffi.NULL:
            return None
        try:
            return ffi.unpack(buffer_address, length).decode("utf-8")
        except Exception:  # invalid utf-8
            return None

    def get_proxied_remote_address_bytes(self):
        buffer = ffi.new("char**")
        length = lib.uws_res_get_proxied_remote_address(self.SSL, self.res, buffer)
        buffer_address = ffi.addressof(buffer, 0)[0]
        if buffer_address == ffi.NULL:
            return None
        try:
            return ffi.unpack(buffer_address, length)
        except Exception:  # invalid
            return None

    def get_proxied_remote_address(self):
        buffer = ffi.new("char**")
        length = lib.uws_res_get_proxied_remote_address_as_text(
            self.SSL, self.res, buffer
        )
        buffer_address = ffi.addressof(buffer, 0)[0]
        if buffer_address == ffi.NULL:
            return None
        try:
            return ffi.unpack(buffer_address, length).decode("utf-8")
        except Exception:  # invalid utf-8
            return None

    def end(self, message, end_connection=False):
        try:
            if self.aborted:
                return self
            if self._write_jar != None:
                self.write_header("Set-Cookie", self._write_jar.output(header=""))
                self._write_jar = None
            if isinstance(message, str):
                data = message.encode("utf-8")
            elif isinstance(message, bytes):
                data = message
            elif message == None:
                self.end_without_body(end_connection)
                return self
            else:
                self.write_header(b"Content-Type", b"application/json")
                data = json.dumps(message).encode("utf-8")
            lib.uws_res_end(
                self.SSL, self.res, data, len(data), 1 if end_connection else 0
            )
        finally:
            return self

    def pause(self):
        if not self.aborted:
            lib.uws_res_pause(self.SSL, self.res)
        return self

    def resume(self):
        if not self.aborted:
            lib.uws_res_resume(self.SSL, self.res)
        return self

    def write_continue(self):
        if not self.aborted:
            lib.uws_res_write_continue(self.SSL, self.res)
        return self

    def write_status(self, status_or_status_text):
        if not self.aborted:
            if isinstance(status_or_status_text, int):
                try:
                    data = status_codes[status_or_status_text]
                except:  # invalid status
                    raise RuntimeError(
                        '"%d" Is not an valid Status Code' % status_or_status_text
                    )
            elif isinstance(status_or_status_text, str):
                data = status_or_status_text.encode("utf-8")
            elif isinstance(status_or_status_text, bytes):
                data = status_or_status_text
            else:
                data = json.dumps(status_or_status_text).encode("utf-8")

            lib.uws_res_write_status(self.SSL, self.res, data, len(data))
        return self

    def write_header(self, key, value):
        if not self.aborted:
            if isinstance(key, str):
                key_data = key.encode("utf-8")
            elif isinstance(key, bytes):
                key_data = key
            else:
                key_data = json.dumps(key).encode("utf-8")

            if isinstance(value, int):
                lib.uws_res_write_header_int(
                    self.SSL,
                    self.res,
                    key_data,
                    len(key_data),
                    ffi.cast("uint64_t", value),
                )
            elif isinstance(value, str):
                value_data = value.encode("utf-8")
            elif isinstance(value, bytes):
                value_data = value
            else:
                value_data = json.dumps(value).encode("utf-8")
            lib.uws_res_write_header(
                self.SSL, self.res, key_data, len(key_data), value_data, len(value_data)
            )
        return self

    def end_without_body(self, end_connection=False):
        if not self.aborted:
            if self._write_jar != None:
                self.write_header("Set-Cookie", self._write_jar.output(header=""))
            lib.uws_res_end_without_body(self.SSL, self.res, 1 if end_connection else 0)
        return self

    def write(self, message):
        if not self.aborted:
            if isinstance(message, str):
                data = message.encode("utf-8")
            elif isinstance(message, bytes):
                data = message
            else:
                data = json.dumps(message).encode("utf-8")
            lib.uws_res_write(self.SSL, self.res, data, len(data))
        return self

    def get_write_offset(self):
        if not self.aborted:
            return int(lib.uws_res_get_write_offset(self.SSL, self.res))
        return 0

    def has_responded(self):
        if self.aborted:
            return False
        return bool(lib.uws_res_has_responded(self.SSL, self.res))

    def on_aborted(self, handler):
        if hasattr(handler, "__call__"):
            self._aborted_handler = handler
            self.grab_aborted_handler()
        return self

    def on_data(self, handler):
        if not self.aborted:
            if hasattr(handler, "__call__"):
                self._data_handler = handler
                self.grab_aborted_handler()
                lib.uws_res_on_data(
                    self.SSL, self.res, uws_generic_on_data_handler, self._ptr
                )
        return self

    def upgrade(
        self,
        sec_web_socket_key,
        sec_web_socket_protocol,
        sec_web_socket_extensions,
        socket_context,
        user_data=None,
    ):
        if self.aborted:
            return False

        if isinstance(sec_web_socket_key, str):
            sec_web_socket_key_data = sec_web_socket_key.encode("utf-8")
        elif isinstance(sec_web_socket_key, bytes):
            sec_web_socket_key_data = sec_web_socket_key
        else:
            sec_web_socket_key_data = b""

        if isinstance(sec_web_socket_protocol, str):
            sec_web_socket_protocol_data = sec_web_socket_protocol.encode("utf-8")
        elif isinstance(sec_web_socket_protocol, bytes):
            sec_web_socket_protocol_data = sec_web_socket_protocol
        else:
            sec_web_socket_protocol_data = b""

        if isinstance(sec_web_socket_extensions, str):
            sec_web_socket_extensions_data = sec_web_socket_extensions.encode("utf-8")
        elif isinstance(sec_web_socket_extensions, bytes):
            sec_web_socket_extensions_data = sec_web_socket_extensions
        else:
            sec_web_socket_extensions_data = b""

        user_data_ptr = ffi.NULL
        if not user_data is None:
            _id = uuid.uuid4()
            user_data_ptr = ffi.new_handle((user_data, _id))
            # keep alive data
            SocketRefs[_id] = user_data_ptr

        lib.uws_res_upgrade(
            self.SSL,
            self.res,
            user_data_ptr,
            sec_web_socket_key_data,
            len(sec_web_socket_key_data),
            sec_web_socket_protocol_data,
            len(sec_web_socket_protocol_data),
            sec_web_socket_extensions_data,
            len(sec_web_socket_extensions_data),
            socket_context,
        )
        return True

    def on_writable(self, handler):
        if not self.aborted:
            if hasattr(handler, "__call__"):
                self._writable_handler = handler
                self.grab_aborted_handler()
                lib.uws_res_on_writable(
                    self.SSL, self.res, uws_generic_on_writable_handler, self._ptr
                )
        return self

    def get_native_handle(self):
        return lib.uws_res_get_native_handle(self.SSL, self.res)

    def __del__(self):
        self.res = ffi.NULL
        self._ptr = ffi.NULL


class App:
    def __init__(self, options=None, request_response_factory_max_itens=0, websocket_factory_max_itens=0):
        socket_options_ptr = ffi.new("struct us_socket_context_options_t *")
        socket_options = socket_options_ptr[0]
        self.options = options
        self._template = None
        if options != None:
            self.is_ssl = True
            self.SSL = ffi.cast("int", 1)
            socket_options.key_file_name = (
                ffi.NULL
                if options.key_file_name == None
                else ffi.new("char[]", options.key_file_name.encode("utf-8"))
            )
            socket_options.key_file_name = (
                ffi.NULL
                if options.key_file_name == None
                else ffi.new("char[]", options.key_file_name.encode("utf-8"))
            )
            socket_options.cert_file_name = (
                ffi.NULL
                if options.cert_file_name == None
                else ffi.new("char[]", options.cert_file_name.encode("utf-8"))
            )
            socket_options.passphrase = (
                ffi.NULL
                if options.passphrase == None
                else ffi.new("char[]", options.passphrase.encode("utf-8"))
            )
            socket_options.dh_params_file_name = (
                ffi.NULL
                if options.dh_params_file_name == None
                else ffi.new("char[]", options.dh_params_file_name.encode("utf-8"))
            )
            socket_options.ca_file_name = (
                ffi.NULL
                if options.ca_file_name == None
                else ffi.new("char[]", options.ca_file_name.encode("utf-8"))
            )
            socket_options.ssl_ciphers = (
                ffi.NULL
                if options.ssl_ciphers == None
                else ffi.new("char[]", options.ssl_ciphers.encode("utf-8"))
            )
            socket_options.ssl_prefer_low_memory_usage = ffi.cast(
                "int", options.ssl_prefer_low_memory_usage
            )
        else:
            self.is_ssl = False
            self.SSL = ffi.cast("int", 0)
        

        self.loop = Loop(
            lambda loop, context, response: self.trigger_error(context, response, None)
        )

        # set async loop to be the last created (is thread_local), App must be one per thread otherwise will use only the lasted loop
        # needs to be called before uws_create_app or otherwise will create another loop and will not receive the right one
        lib.uws_get_loop_with_native(self.loop.get_native_loop())
        self.app = lib.uws_create_app(self.SSL, socket_options)
        self._ptr = ffi.new_handle(self)
        if bool(lib.uws_constructor_failed(self.SSL, self.app)):
            raise RuntimeError("Failed to create connection")

        self.handlers = []
        self.error_handler = None
        self._missing_server_handler = None

        if request_response_factory_max_itens and request_response_factory_max_itens >= 1:
            self._factory = RequestResponseFactory(self, request_response_factory_max_itens)
        else: 
            self._factory = None

        if websocket_factory_max_itens and websocket_factory_max_itens >= 1:
            self._ws_factory = WebSocketFactory(self, websocket_factory_max_itens)
        else: 
            self._ws_factory = None
        
    def template(self, template_engine):
        self._template = template_engine

    def static(self, route, directory):
        static_route(self, route, directory)
        return self

    def get(self, path, handler):
        user_data = ffi.new_handle((handler, self))
        self.handlers.append(user_data)  # Keep alive handler
        lib.uws_app_get(
            self.SSL,
            self.app,
            path.encode("utf-8"),
            uws_generic_factory_method_handler if self._factory else uws_generic_method_handler,
            user_data,
        )
        return self

    def post(self, path, handler):
        user_data = ffi.new_handle((handler, self))
        self.handlers.append(user_data)  # Keep alive handler
        lib.uws_app_post(
            self.SSL,
            self.app,
            path.encode("utf-8"),
            uws_generic_factory_method_handler if self._factory else uws_generic_method_handler,
            user_data,
        )
        return self

    def options(self, path, handler):
        user_data = ffi.new_handle((handler, self))
        self.handlers.append(user_data)  # Keep alive handler
        lib.uws_app_options(
            self.SSL,
            self.app,
            path.encode("utf-8"),
            uws_generic_factory_method_handler if self._factory else uws_generic_method_handler,
            user_data,
        )
        return self

    def delete(self, path, handler):
        user_data = ffi.new_handle((handler, self))
        self.handlers.append(user_data)  # Keep alive handler
        lib.uws_app_delete(
            self.SSL,
            self.app,
            path.encode("utf-8"),
            uws_generic_factory_method_handler if self._factory else uws_generic_method_handler,
            user_data,
        )
        return self

    def patch(self, path, handler):
        user_data = ffi.new_handle((handler, self))
        self.handlers.append(user_data)  # Keep alive handler
        lib.uws_app_patch(
            self.SSL,
            self.app,
            path.encode("utf-8"),
            uws_generic_factory_method_handler if self._factory else uws_generic_method_handler,
            user_data,
        )
        return self

    def put(self, path, handler):
        user_data = ffi.new_handle((handler, self))
        self.handlers.append(user_data)  # Keep alive handler
        lib.uws_app_put(
            self.SSL,
            self.app,
            path.encode("utf-8"),
            uws_generic_factory_method_handler if self._factory else uws_generic_method_handler,
            user_data,
        )
        return self

    def head(self, path, handler):
        user_data = ffi.new_handle((handler, self))
        self.handlers.append(user_data)  # Keep alive handler
        lib.uws_app_head(
            self.SSL,
            self.app,
            path.encode("utf-8"),
            uws_generic_factory_method_handler if self._factory else uws_generic_method_handler,
            user_data,
        )
        return self

    def connect(self, path, handler):
        user_data = ffi.new_handle((handler, self))
        self.handlers.append(user_data)  # Keep alive handler
        lib.uws_app_connect(
            self.SSL,
            self.app,
            path.encode("utf-8"),
            uws_generic_factory_method_handler if self._factory else uws_generic_method_handler,
            user_data,
        )
        return self

    def trace(self, path, handler):
        user_data = ffi.new_handle((handler, self))
        self.handlers.append(user_data)  # Keep alive handler
        lib.uws_app_trace(
            self.SSL,
            self.app,
            path.encode("utf-8"),
            uws_generic_factory_method_handler if self._factory else uws_generic_method_handler,
            user_data,
        )
        return self

    def any(self, path, handler):
        user_data = ffi.new_handle((handler, self))
        self.handlers.append(user_data)  # Keep alive handler
        lib.uws_app_any(
            self.SSL,
            self.app,
            path.encode("utf-8"),
            uws_generic_factory_method_handler if self._factory else uws_generic_method_handler,
            user_data,
        )
        return self

    def get_native_handle(self):
        return lib.uws_get_native_handle(self.SSL, self.app)

    def num_subscribers(self, topic):
        if isinstance(topic, str):
            topic_data = topic.encode("utf-8")
        elif isinstance(topic, bytes):
            topic_data = topic
        else:
            raise RuntimeError("topic need to be an String or Bytes")
        return int(
            lib.uws_num_subscribers(self.SSL, self.app, topic_data, len(topic_data))
        )

    def publish(self, topic, message, opcode=OpCode.BINARY, compress=False):

        if isinstance(topic, str):
            topic_data = topic.encode("utf-8")
        elif isinstance(topic, bytes):
            topic_data = topic
        else:
            raise RuntimeError("topic need to be an String or Bytes")

        if isinstance(message, str):
            message_data = message.encode("utf-8")
        elif isinstance(message, bytes):
            message_data = message
        elif message == None:
            data = b""
        else:
            data = json.dumps(message).encode("utf-8")

        return bool(
            lib.uws_publish(
                self.SSL,
                self.app,
                topic_data,
                len(topic_data),
                message_data,
                len(message_data),
                int(opcode),
                bool(compress),
            )
        )

    def remove_server_name(self, hostname):
        if isinstance(hostname, str):
            hostname_data = hostname.encode("utf-8")
        elif isinstance(hostname, bytes):
            hostname_data = hostname
        else:
            raise RuntimeError("hostname need to be an String or Bytes")

        lib.uws_remove_server_name(
            self.SSL, self.app, hostname_data, len(hostname_data)
        )
        return self

    def add_server_name(self, hostname, options=None):
        if isinstance(hostname, str):
            hostname_data = hostname.encode("utf-8")
        elif isinstance(hostname, bytes):
            hostname_data = hostname
        else:
            raise RuntimeError("hostname need to be an String or Bytes")

        if options is None:
            lib.uws_add_server_name(
                self.SSL, self.app, hostname_data, len(hostname_data)
            )
        else:
            socket_options_ptr = ffi.new("struct us_socket_context_options_t *")
            socket_options = socket_options_ptr[0]
            socket_options.key_file_name = (
                ffi.NULL
                if options.key_file_name == None
                else ffi.new("char[]", options.key_file_name.encode("utf-8"))
            )
            socket_options.key_file_name = (
                ffi.NULL
                if options.key_file_name == None
                else ffi.new("char[]", options.key_file_name.encode("utf-8"))
            )
            socket_options.cert_file_name = (
                ffi.NULL
                if options.cert_file_name == None
                else ffi.new("char[]", options.cert_file_name.encode("utf-8"))
            )
            socket_options.passphrase = (
                ffi.NULL
                if options.passphrase == None
                else ffi.new("char[]", options.passphrase.encode("utf-8"))
            )
            socket_options.dh_params_file_name = (
                ffi.NULL
                if options.dh_params_file_name == None
                else ffi.new("char[]", options.dh_params_file_name.encode("utf-8"))
            )
            socket_options.ca_file_name = (
                ffi.NULL
                if options.ca_file_name == None
                else ffi.new("char[]", options.ca_file_name.encode("utf-8"))
            )
            socket_options.ssl_ciphers = (
                ffi.NULL
                if options.ssl_ciphers == None
                else ffi.new("char[]", options.ssl_ciphers.encode("utf-8"))
            )
            socket_options.ssl_prefer_low_memory_usage = ffi.cast(
                "int", options.ssl_prefer_low_memory_usage
            )
            lib.uws_add_server_name_with_options(
                self.SSL, self.app, hostname_data, len(hostname_data), socket_options
            )
        return self

    def missing_server_name(self, handler):
        self._missing_server_handler = handler
        lib.uws_missing_server_name(
            self.SSL, self.app, uws_missing_server_name, self._ptr
        )

    def ws(self, path, behavior):
        native_options = ffi.new("uws_socket_behavior_t *")
        native_behavior = native_options[0]

        max_payload_length = None
        idle_timeout = None
        max_backpressure = None
        close_on_backpressure_limit = None
        reset_idle_timeout_on_send = None
        send_pings_automatically = None
        max_lifetime = None
        compression = None
        upgrade_handler = None
        open_handler = None
        message_handler = None
        drain_handler = None
        ping_handler = None
        pong_handler = None
        close_handler = None

        if behavior is None:
            raise RuntimeError("behavior must be an dict or WSBehavior")
        elif isinstance(behavior, dict):
            max_payload_length = behavior.get("max_payload_length", 16 * 1024)
            idle_timeout = behavior.get("idle_timeout", 60 * 2)
            max_backpressure = behavior.get("max_backpressure", 64 * 1024)
            close_on_backpressure_limit = behavior.get(
                "close_on_backpressure_limit", False
            )
            reset_idle_timeout_on_send = behavior.get(
                "reset_idle_timeout_on_send", False
            )
            send_pings_automatically = behavior.get("send_pings_automatically", False)
            max_lifetime = behavior.get("max_lifetime", 0)
            compression = behavior.get("compression", 0)
            upgrade_handler = behavior.get("upgrade", None)
            open_handler = behavior.get("open", None)
            message_handler = behavior.get("message", None)
            drain_handler = behavior.get("drain", None)
            ping_handler = behavior.get("ping", None)
            pong_handler = behavior.get("pong", None)
            close_handler = behavior.get("close", None)

        native_behavior.maxPayloadLength = ffi.cast(
            "unsigned int",
            max_payload_length if isinstance(max_payload_length, int) else 16 * 1024,
        )
        native_behavior.idleTimeout = ffi.cast(
            "unsigned short",
            idle_timeout if isinstance(idle_timeout, int) else 16 * 1024,
        )
        native_behavior.maxBackpressure = ffi.cast(
            "unsigned int",
            max_backpressure if isinstance(max_backpressure, int) else 64 * 1024,
        )
        native_behavior.compression = ffi.cast(
            "uws_compress_options_t", compression if isinstance(compression, int) else 0
        )
        native_behavior.maxLifetime = ffi.cast(
            "unsigned short", max_lifetime if isinstance(max_lifetime, int) else 0
        )
        native_behavior.closeOnBackpressureLimit = ffi.cast(
            "int", 1 if close_on_backpressure_limit else 0
        )
        native_behavior.resetIdleTimeoutOnSend = ffi.cast(
            "int", 1 if reset_idle_timeout_on_send else 0
        )
        native_behavior.sendPingsAutomatically = ffi.cast(
            "int", 1 if send_pings_automatically else 0
        )

        handlers = WSBehaviorHandlers()
        if upgrade_handler:
            handlers.upgrade = upgrade_handler
            native_behavior.upgrade = uws_websocket_factory_upgrade_handler if self._factory else uws_websocket_upgrade_handler
        else:
            native_behavior.upgrade = ffi.NULL

        if open_handler:
            handlers.open = open_handler
            native_behavior.open = uws_websocket_factory_open_handler if self._ws_factory else uws_websocket_open_handler
        else:
            native_behavior.open = ffi.NULL

        if message_handler:
            handlers.message = message_handler
            native_behavior.message = uws_websocket_factory_message_handler if self._ws_factory else uws_websocket_message_handler
        else:
            native_behavior.message = ffi.NULL

        if drain_handler:
            handlers.drain = drain_handler
            native_behavior.drain = uws_websocket_factory_drain_handler if self._ws_factory else uws_websocket_drain_handler
        else:
            native_behavior.drain = ffi.NULL

        if ping_handler:
            handlers.ping = ping_handler
            native_behavior.ping = uws_websocket_factory_ping_handler if self._ws_factory else uws_websocket_ping_handler
        else:
            native_behavior.ping = ffi.NULL

        if pong_handler:
            handlers.pong = pong_handler
            native_behavior.pong = uws_websocket_factory_pong_handler if self._ws_factory else uws_websocket_pong_handler
        else:
            native_behavior.pong = ffi.NULL

        if close_handler:
            handlers.close = close_handler
            native_behavior.close = uws_websocket_factory_close_handler if self._ws_factory else uws_websocket_close_handler
        else:  # always keep an close
            native_behavior.close = uws_websocket_close_handler

        user_data = ffi.new_handle((handlers, self))
        self.handlers.append(user_data)  # Keep alive handlers
        lib.uws_ws(self.SSL, self.app, path.encode("utf-8"), native_behavior, user_data)
        return self

    def listen(self, port_or_options=None, handler=None):
        self._listen_handler = handler
        if port_or_options is None:
            lib.uws_app_listen(
                self.SSL,
                self.app,
                ffi.cast("int", 0),
                uws_generic_listen_handler,
                self._ptr,
            )
        elif isinstance(port_or_options, int):
            lib.uws_app_listen(
                self.SSL,
                self.app,
                ffi.cast("int", port_or_options),
                uws_generic_listen_handler,
                self._ptr,
            )
        elif isinstance(port_or_options, dict):
            native_options = ffi.new("uws_app_listen_config_t *")
            options = native_options[0]
            port = port_or_options.get("port", 0)
            options = port_or_options.get("options", 0)
            host = port_or_options.get("host", "0.0.0.0")
            options.port = (
                ffi.cast("int", port, 0)
                if isinstance(port, int)
                else ffi.cast("int", 0)
            )
            options.host = (
                ffi.new("char[]", host.encode("utf-8"))
                if isinstance(host, str)
                else ffi.NULL
            )
            options.options = (
                ffi.cast("int", port)
                if isinstance(options, int)
                else ffi.cast("int", 0)
            )
            self.native_options_listen = native_options  # Keep alive native_options
            lib.uws_app_listen_with_config(
                self.SSL, self.app, options, uws_generic_listen_handler, self._ptr
            )
        else:
            native_options = ffi.new("uws_app_listen_config_t *")
            options = native_options[0]
            options.port = ffi.cast("int", port_or_options.port)
            options.host = (
                ffi.NULL
                if port_or_options.host == None
                else ffi.new("char[]", port_or_options.host.encode("utf-8"))
            )
            options.options = ffi.cast("int", port_or_options.options)
            self.native_options_listen = native_options  # Keep alive native_options
            lib.uws_app_listen_with_config(
                self.SSL, self.app, options, uws_generic_listen_handler, self._ptr
            )

        return self

    def run_async(self, task, response=None):
        return self.loop.run_async(task, response)

    def run(self):
        signal.signal(signal.SIGINT, lambda sig, frame: self.close())
        self.loop.start()
        self.loop.run()
        return self

    def close(self):
        if hasattr(self, "socket"):
            if not self.socket == ffi.NULL:
                lib.us_listen_socket_close(self.SSL, self.socket)
                self.loop.stop()
        return self

    def set_error_handler(self, handler):
        if hasattr(handler, "__call__"):
            self.error_handler = handler
        else:
            self.error_handler = None

    def trigger_error(self, error, response, request):
        if self.error_handler == None:
            try:
                print(
                    "Uncaught Exception: %s" % str(error)
                )  # just log in console the error to call attention
                response.write_status(500).end("Internal Error")
            finally:
                return
        else:
            try:
                if inspect.iscoroutinefunction(self.error_handler):
                    self.run_async(
                        self.error_handler(error, response, request), response
                    )
                else:
                    self.error_handler(error, response, request)
            except Exception as error:
                try:
                    # Error handler got an error :D
                    print(
                        "Uncaught Exception: %s" % str(error)
                    )  # just log in console the error to call attention
                    response.write_status(500).end("Internal Error")
                finally:
                    pass

    def __del__(self):
        lib.uws_app_destroy(self.SSL, self.app)


class AppListenOptions:
    def __init__(self, port=0, host=None, options=0):
        if not isinstance(port, int):
            raise RuntimeError("port must be an int")
        if host != None and not isinstance(host, str):
            raise RuntimeError("host must be an String or None")
        if not isinstance(options, int):
            raise RuntimeError("options must be an int")
        self.port = port
        self.host = host
        self.options = options


class AppOptions:
    def __init__(
        self,
        key_file_name=None,
        cert_file_name=None,
        passphrase=None,
        dh_params_file_name=None,
        ca_file_name=None,
        ssl_ciphers=None,
        ssl_prefer_low_memory_usage=0
    ):
        if key_file_name != None and not isinstance(key_file_name, str):
            raise RuntimeError("key_file_name must be an String or None")
        if cert_file_name != None and not isinstance(cert_file_name, str):
            raise RuntimeError("cert_file_name must be an String or None")
        if passphrase != None and not isinstance(passphrase, str):
            raise RuntimeError("passphrase must be an String or None")
        if dh_params_file_name != None and not isinstance(dh_params_file_name, str):
            raise RuntimeError("dh_params_file_name must be an String or None")
        if ca_file_name != None and not isinstance(ca_file_name, str):
            raise RuntimeError("ca_file_name must be an String or None")
        if ssl_ciphers != None and not isinstance(ssl_ciphers, str):
            raise RuntimeError("ssl_ciphers must be an String or None")
        if not isinstance(ssl_prefer_low_memory_usage, int):
            raise RuntimeError("ssl_prefer_low_memory_usage must be an int")

        self.key_file_name = key_file_name
        self.cert_file_name = cert_file_name
        self.passphrase = passphrase
        self.dh_params_file_name = dh_params_file_name
        self.ca_file_name = ca_file_name
        self.ssl_ciphers = ssl_ciphers
        self.ssl_prefer_low_memory_usage = ssl_prefer_low_memory_usage
