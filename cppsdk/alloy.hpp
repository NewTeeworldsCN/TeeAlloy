/*
MIT License

Copyright (c) 2025 NewTeeworldsCN

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/
#ifndef __ALLOY_HPP__
#define __ALLOY_HPP__

#define CPPHTTPLIB_OPENSSL_SUPPORT
#include "httplib.h"
#include "json.hpp"

#include <string>
#include <functional>
#include <future>
#include <thread>
#include <memory>

namespace teealloy
{

    // ------------------------
    // type define
    // ------------------------

    enum class ErrorCode
    {
        OK,
        NetworkError,
        HTTPError,
        AuthFailed,
        ParseError
    };

    struct Result
    {
        bool success;
        ErrorCode error_code;
        std::string error_message;

        Result(bool s = false, ErrorCode ec = ErrorCode::OK, const std::string &msg = "")
            : success(s), error_code(ec), error_message(msg) {}

        operator bool() const { return success; }
    };

    struct UserInfo
    {
        std::string user_id;
        std::string username;
        std::string nickname;
        int reputation = 0;
        std::string created_at;
    };

    // ------------------------
    // class
    // ------------------------

    class AuthClient
    {
    public:
        using VerifyCallback = std::function<void(Result, UserInfo)>;

        explicit AuthClient(const std::string &host, const std::string &server_address, const std::string &api_key)
            : host_(host), server_address(server_address), api_key_(api_key), use_ssl_(true), ca_cert_path_("")
        {
            parse_host(host);
        }

        void set_ca_cert_path(const std::string &path)
        {
            ca_cert_path_ = path;
        }

        void set_thread_pool_size(int n)
        {
            thread_pool_size_ = (n > 0) ? n : 1;
        }

        Result health_check();
        Result verify_game_token(const std::string &game_token, UserInfo &out_user);
        void verify_game_token_async(const std::string &game_token, VerifyCallback callback);

    private:
        std::string host_;
        std::string host_clean_;
        std::string server_address;
        std::string api_key_;
        bool use_ssl_;
        std::string ca_cert_path_;
        int thread_pool_size_ = 2;

        void parse_host(const std::string &host);
        Result handle_response(const void *res_ptr, bool is_ssl);
    };

    // ------------------------
    // impl
    // ------------------------

    inline void AuthClient::parse_host(const std::string &host)
    {
        if (host.size() >= 8 && host.substr(0, 8) == "https://")
        {
            host_clean_ = host.substr(8);
            use_ssl_ = true;
        }
        else if (host.size() >= 7 && host.substr(0, 7) == "http://")
        {
            host_clean_ = host.substr(7);
            use_ssl_ = false;
        }
        else
        {
            host_clean_ = host;
            use_ssl_ = true; // 默认 HTTPS
        }
    }

    inline Result AuthClient::health_check()
    {
        try
        {
            if (use_ssl_)
            {
                httplib::SSLClient cli(host_clean_.c_str());
                if (!ca_cert_path_.empty())
                {
                    cli.set_ca_cert_path(ca_cert_path_.c_str());
                }
                cli.set_connection_timeout(5);
                cli.set_read_timeout(10);

                auto res = cli.Get("/api/v1/healthz");
                if (res && res->status == 200)
                {
                    auto j = nlohmann::json::parse(res->body);
                    if (j.value("status", "") == "ok")
                    {
                        return {true, ErrorCode::OK, ""};
                    }
                }
                return {false, ErrorCode::HTTPError, "Health check failed"};
            }
            else
            {
                httplib::Client cli(("http://" + host_clean_).c_str());
                cli.set_connection_timeout(5);
                cli.set_read_timeout(10);

                auto res = cli.Get("/api/v1/healthz");
                if (res && res->status == 200)
                {
                    auto j = nlohmann::json::parse(res->body);
                    if (j.value("status", "") == "ok")
                    {
                        return {true, ErrorCode::OK, ""};
                    }
                }
                return {false, ErrorCode::HTTPError, "Health check failed"};
            }
        }
        catch (const std::exception &e)
        {
            return {false, ErrorCode::NetworkError, std::string("Exception: ") + e.what()};
        }
    }

    inline Result AuthClient::verify_game_token(const std::string &game_token, UserInfo &out_user)
    {
        try
        {
            nlohmann::json payload = {{"game_token", game_token}};
            std::string body = payload.dump();
            httplib::Headers headers{
                {"Content-Type", "application/json"},
                {"X-Server-Address", server_address},
                {"X-API-Key", api_key_}};

            if (use_ssl_)
            {
                httplib::SSLClient cli(host_clean_.c_str());
                if (!ca_cert_path_.empty())
                {
                    cli.set_ca_cert_path(ca_cert_path_.c_str());
                }
                cli.set_connection_timeout(5);
                cli.set_read_timeout(10);

                auto res = cli.Post("/api/v1/auth/verify-game-token", headers, body, "application/json");
                auto result = handle_response(&res, true);
                if (result)
                {
                    auto j = nlohmann::json::parse(res->body);
                    auto user = j["user"];
                    out_user.user_id = user.value("user_id", "");
                    out_user.username = user.value("username", "");
                    out_user.nickname = user.value("nickname", "");
                    out_user.reputation = user.value("reputation", 0);
                    out_user.created_at = user.value("created_at", "");
                }
                return result;
            }
            else
            {
                httplib::Client cli(("http://" + host_clean_).c_str());
                cli.set_connection_timeout(5);
                cli.set_read_timeout(10);

                auto res = cli.Post("/api/v1/auth/verify-game-token", headers, body, "application/json");
                auto result = handle_response(&res, false);
                if (result)
                {
                    auto j = nlohmann::json::parse(res->body);
                    auto user = j["user"];
                    out_user.user_id = user.value("user_id", "");
                    out_user.username = user.value("username", "");
                    out_user.nickname = user.value("nickname", "");
                    out_user.reputation = user.value("reputation", 0);
                    out_user.created_at = user.value("created_at", "");
                }
                return result;
            }
        }
        catch (...)
        {
            return {false, ErrorCode::NetworkError, "Request failed"};
        }
    }

    inline Result AuthClient::handle_response(const void *res_ptr, bool is_ssl)
    {
        if (is_ssl)
        {
            const auto *res = static_cast<const httplib::Result *>(res_ptr);
            if (!*res)
            {
                return {false, ErrorCode::NetworkError, "No response (SSL)"};
            }
            if ((*res)->status != 200)
            {
                try
                {
                    auto j = nlohmann::json::parse((*res)->body);
                    return {false, ErrorCode::AuthFailed, j.value("error", "unknown")};
                }
                catch (...)
                {
                    return {false, ErrorCode::HTTPError, "HTTP " + std::to_string((*res)->status)};
                }
            }
            try
            {
                auto j = nlohmann::json::parse((*res)->body);
                if (j.value("success", false))
                {
                    return {true, ErrorCode::OK, ""};
                }
                else
                {
                    return {false, ErrorCode::AuthFailed, j.value("error", "unknown")};
                }
            }
            catch (...)
            {
                return {false, ErrorCode::ParseError, "JSON parse error"};
            }
        }
        else
        {
            const auto *res = static_cast<const httplib::Response *>(res_ptr);
            if (!res)
            {
                return {false, ErrorCode::NetworkError, "No response (HTTP)"};
            }
            if (res->status != 200)
            {
                return {false, ErrorCode::HTTPError, "HTTP " + std::to_string(res->status)};
            }
            try
            {
                auto j = nlohmann::json::parse(res->body);
                if (j.value("success", false))
                {
                    return {true, ErrorCode::OK, ""};
                }
                else
                {
                    return {false, ErrorCode::AuthFailed, j.value("error", "unknown")};
                }
            }
            catch (...)
            {
                return {false, ErrorCode::ParseError, "JSON parse error"};
            }
        }
    }

    inline void AuthClient::verify_game_token_async(const std::string &game_token, VerifyCallback callback)
    {
        std::thread([=]()
                    {
        UserInfo user;
        Result result = verify_game_token(game_token, user);
        if (callback) {
            callback(result, user);
        } })
            .detach();
    }

} // namespace teealloy

#endif // __ALLOY_HPP__
