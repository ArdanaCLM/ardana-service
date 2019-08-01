# (c) Copyright 2017-2019 SUSE LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from functools import reduce
import ipaddress
import operator
import requests
import socket
import sys

TIMEOUT = 2


# Forward the url to the given destination
def forward(url, request):

    req = requests.Request(method=request.method, url=url, params=request.args,
                           headers=request.headers, data=request.data)

    resp = requests.Session().send(req.prepare())

    return (resp.text, resp.status_code, resp.headers.items())


def ping(host, port):
    # Use getaddrinfo to properly and automatically handle both ipv4 and v6
    for res in socket.getaddrinfo(
            host, port, socket.AF_UNSPEC, socket.SOCK_STREAM):

        af, socktype, proto, canonname, sa = res
        try:
            s = socket.socket(af, socktype, proto)
        except OSError as msg:
            s = None
            continue

        s.settimeout(TIMEOUT)
        try:
            s.connect(sa)
            return

        except OSError as e:
            last_error = e

    if last_error:
        raise last_error


def find(element, dictionary):
    return reduce(operator.getitem, element.split('.'), dictionary)


def is_ipv6(address):

    # ipaddress requires unicode arguments (all strings in python3 are already
    # unicode)
    addr = address
    if sys.version_info.major == 2:
        addr = unicode(address)    # noqa: F821

    try:
        ipaddress.IPv6Address(addr)
        return True
    except Exception:
        return False


def url_address(host_or_ip):
    if ':' in host_or_ip and is_ipv6(host_or_ip):
        return '[' + host_or_ip + ']'

    return host_or_ip
