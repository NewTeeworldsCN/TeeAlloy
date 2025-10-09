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
#include <iostream>
#include "alloy.hpp"

int main()
{
    teealloy::AuthClient client("<Target>", "<Address>", "sk_live_<APIKEY>");
    auto result = client.health_check();

    if (result)
    {
        std::cout << "Health check passed" << std::endl;
    }
    else
    {
        std::cerr << "Error: " << result.error_message << std::endl;
    }

    client.verify_game_token_async("TOKEN", "NICKNAME", [](teealloy::Result res, teealloy::UserInfo u)
    {
        if (res)
        {
            std::cout << "[Async] Success: " << u.nickname << "\n";
        } else {
            std::cerr << "[Async] Failed: " << res.error_message << "\n";
        }
    });

    std::this_thread::sleep_for(std::chrono::seconds(2));

    return 0;
}