# -*- coding: iso-8859-1 -*-
"""
    Functional test suite for WsgiDAV. 
    
    This test suite uses davclient to generate WebDAV requests.
     
    See http://chandlerproject.org/Projects/Davclient
        http://svn.osafoundation.org/tools/davclient/trunk/src/davclient/davclient.py
"""
from tempfile import gettempdir
from wsgidav.wsgidav_app import DEFAULT_CONFIG, WsgiDAVApp
from wsgidav.fs_dav_provider import FilesystemProvider
#from wsgidav.server import ext_wsgiutils_server
#from wsgidav import util
from wsgidav.server.ext_wsgiutils_server import ExtServer
from pprint import pprint
import time
import os
import unittest
import davclient #@UnresolvedImport
from threading import Thread


#===============================================================================
# EXTERNAL_SERVER_ADDRESS
# <None> means 'start WsgiDAV as parallel thread'
#
# When the PyDev Debugger is running, then davclient requests will block 
# (i.e. will not be handled by WsgiDAVServerThread)
# In this case, run WsgiDAV as external process and specify the URL here.
# This is also recommended when doing benchmarks
#===============================================================================
EXTERNAL_SERVER_ADDRESS = None
#EXTERNAL_SERVER_ADDRESS = "http://127.0.0.1:8080"

#===============================================================================
# WsgiDAVServerThread
#===============================================================================
class WsgiDAVServerThread(Thread):
    """WsgiDAV server that can be run in a parallel thread."""
    def __init__ (self):
        Thread.__init__(self)
        self.ext_server = None

    def __del__(self):
        self.shutdown()
            
    def run(self):
        withAuthentication = True
        self.rootpath = os.path.join(gettempdir(), "wsgidav-test")
        if not os.path.exists(self.rootpath):
            os.mkdir(self.rootpath)
        provider = FilesystemProvider(self.rootpath)
                
        config = DEFAULT_CONFIG.copy()
        config.update({
            "provider_mapping": {"/": provider},
            "user_mapping": {},
            "host": "localhost",
            "port": 8080,
            "enable_loggers": [ ],
            "debug_methods": [ ],
            "propsmanager": True,      # True: use lock_manager.LockManager           
            "locksmanager": True,      # True: use lock_manager.LockManager                   
            "domaincontroller": None,  # None: domain_controller.WsgiDAVDomainController(user_mapping)
            "verbose": 2,
            })

        if withAuthentication:
            config["user_mapping"] = {"/": {"tester": {"password": "tester",
                                                       "description": "",
                                                       "roles": [],
                                                       },
                                            },
                                      }
            config["acceptbasic"] = True
            config["acceptdigest"] = False
            config["defaultdigest"] = False
        
        app = WsgiDAVApp(config)
        
        self.ext_server = ExtServer((config["host"], config["port"]), 
                                    {"": app})

        self.ext_server.serve_forever_stoppable()
        self.ext_server = None
#        print "WsgiDAVServerThread.run() terminated"

    def shutdown(self):
        if self.ext_server:
#            print "WsgiDAVServerThread.shutdown()..."
            # let server process pending requests, otherwise shutdown might lock
            time.sleep(.1)
            self.ext_server.stop_serve_forever()
#            try:
#                # since Python 2.6
#                self.ext_server.shutdown()
#            except AttributeError:
#                pass
            self.ext_server = None
#            print "WsgiDAVServerThread.shutdown()... complete"

#===============================================================================
# ServerTest
#===============================================================================
class ServerTest(unittest.TestCase):                          
    """Test wsgidav_app using davclient."""

    @classmethod
    def suite(cls):
        """Return test case suite (so we can control the order)."""
        suite = unittest.TestSuite()
        suite.addTest(cls("testPreconditions"))
        suite.addTest(cls("testGetPut"))
        return suite


    def setUp(self):
#        print "setUp"
        if EXTERNAL_SERVER_ADDRESS:
            self.server_thread = None
            self.client = davclient.DAVClient(EXTERNAL_SERVER_ADDRESS)
        else:
            self.server_thread = WsgiDAVServerThread()
            self.server_thread.start()
            # let server start the loop, otherwise shutdown might lock
            time.sleep(.1)
            self.client = davclient.DAVClient("http://127.0.0.1:8080/")

        self.client.set_basic_auth("tester", "tester")
#        self.client.headers['new_header_for_session'] = "useful_example"


    def tearDown(self):
#        print "tearDown"
        del self.client
        if self.server_thread:
            self.server_thread.shutdown()
    #        print "tearDown join..."
            self.server_thread.join()
            self.server_thread = None         
    #        print "tearDown joined"
#        os.rmdir(self.rootpath)


    def testPreconditions(self):                          
        """Environment must be set."""
        self.assertTrue(__debug__, "__debug__ must be True, otherwise asserts are ignored")


    def testGetPut(self):                          
        """Read and write file contents."""
        client = self.client

        # Prepare file content
        data1 = "this is a file\nwith two lines"
        data2 = "this is another file\nwith three lines\nsee?"
        # Big file with 10 MB
        lines = []
        line = "." * (1000-6-len("\n"))
        for i in xrange(10*1000):
            lines.append("%04i: %s\n" % (i, line))
        data3 = "".join(lines)

        # Cleanup
        client.delete("/test/")
        client.mkcol("/test/")
        client.checkResponse(201)

        # PUT files
        client.put("/test/file1.txt", data1)
        client.checkResponse(201)
        client.put("/test/file2.txt", data2)
        client.checkResponse(201)
        client.put("/test/bigfile.txt", data3)
        client.checkResponse(201)

        body = client.get("/test/file1.txt")
        client.checkResponse(200)
#        print body

        # PUT with overwrite must return 204 No Content, instead of 201 Created
        client.put("/test/file2.txt", data2)
        client.checkResponse(204)

        client.mkcol("/test/folder")
        client.checkResponse(201)
        
        locks = client.set_lock("/test/lock-0", 
                                owner="test-bench", 
                                locktype="write", 
                                lockscope="exclusive", 
                                depth="infinity")
        client.checkResponse(201)
        assert len(locks) == 1, "LOCK failed"
        token = locks[0]
        client.refresh_lock("/test/lock-0", token)
        client.checkResponse()
        client.unlock("/test/lock-0", token)         
        client.checkResponse(204)
        client.unlock("/test/lock-0", token)         
#        client.checkResponse()
         
        client.proppatch("/test/file1.txt", 
                         set_props=[("{testns:}testname", "testval"),
                                    ], 
                         remove_props=None)
        client.checkResponse()

        client.copy("/test/file1.txt", 
                    "/test/file2.txt", 
                    depth='infinity', overwrite=True) 
        client.checkResponse()

        client.move("/test/file2.txt", 
                    "/test/file2_moved.txt", 
                    depth='infinity', overwrite=True) 
        client.checkResponse()

        client.propfind("/", 
                        properties="allprop", 
                        namespace='DAV:', 
                        depth=None, 
                        headers=None)
        client.checkResponse()
        
#        print client.response.tree
        
#        print dict(client.response.getheaders())
         
#        # Remove old test files
#        
#        # Access unmapped resource (expect '404 Not Found')
#        app.delete("/file1.txt", status=404)
#        app.get("/file1.txt", status=404)
#        
#        # PUT a small file (expect '201 Created')
#        app.put("/file1.txt", params=data1, status=201)
#        
#        res = app.get("/file1.txt", status=200)
#        assert res.body == data1, "GET file content different from PUT"
#
#        # PUT overwrites a small file (expect '204 No Content')
#        app.put("/file1.txt", params=data2, status=204)
#        
#        res = app.get("/file1.txt", status=200)
#        assert res.body == data2, "GET file content different from PUT"
#
#        # PUT writes a big file (expect '201 Created')
#        app.put("/file2.txt", params=data3, status=201)
#
#        res = app.get("/file2.txt", status=200)
#        assert res.body == data3, "GET file content different from PUT"
#
#        # Request must not contain a body (expect '415 Media Type Not Supported')
#        app.get("/file1.txt", 
#                headers={"Content-Length": str(len(data1))},
#                params=data1, 
#                status=415)
#
#        # Delete existing resource (expect '204 No Content')
#        app.delete("/file1.txt", status=204)
#        # Get deleted resource (expect '404 Not Found')
#        app.get("/file1.txt", status=404)
#
#        # PUT a small file (expect '201 Created')
#        app.put("/file1.txt", params=data1, status=201)
        



#===============================================================================
# suite
#===============================================================================
def suite():
    """Return suites of all test cases."""
    return unittest.TestSuite([ServerTest.suite(), 
                               ])  


if __name__ == "__main__":
#    unittest.main()
#    global EXTERNAL_SERVER_ADDRESS
#    EXTERNAL_SERVER_ADDRESS = "http://127.0.0.1:8080"
#    print "Using external server to enable debugging: ", EXTERNAL_SERVER_ADDRESS
    
    suite = suite()
    unittest.TextTestRunner(descriptions=1, verbosity=2).run(suite)
