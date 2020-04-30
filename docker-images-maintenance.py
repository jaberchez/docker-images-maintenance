#! /usr/bin/python3

###################################################################################################################
# Description: Script to perform docker image maintenance
###################################################################################################################

# Imports
#------------------------------------------------------------------------------------------------------------------
from packaging import version

import os
import sys
import re
import signal
import subprocess
#------------------------------------------------------------------------------------------------------------------

# Functions
#==================================================================================================================
# Description: Handle signals
# Parameters:  Signal and frame of the object
# Return:      Nothing, just exit

def signal_handler(sig, frame):
   name_signal = ''

   if sig == 2:
      name_signal = "SIGINT"
   elif sig == 15:
      name_signal = "SIGTERM"
   else:
      name_signal = "UNKNOWN"

   print("\nCatch signal: " + name_signal)
   sys.exit(1)
#==================================================================================================================

#==================================================================================================================
# Description: Main function
# Parameters:  None
# Return:      Nothing, just finish the script

def main():
   prune_images()
   clean_dangling_images()
   clean_none_images()
   clean_duplicate_images()
   clean_unused_images()
#==================================================================================================================

#==================================================================================================================
# Description: Perform docker system prune
# Parameters:  None
# Return:      Nothing. It doesn't matter wether the command finishes correctly or not 

def prune_images():
   print("Executing \"prune images\"")

   cmd = "docker system prune -f"
   p   = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

   p.communicate()
#==================================================================================================================

#==================================================================================================================
# Description: Clean dangling images
# Parameters:  None
# Return:      Nothing. It doesn't matter wether the command finishes correctly or not 

def clean_dangling_images():
   print("Executing \"clean dangling images\"")

   c          = "docker images -f \"dangling=true\" -q"
   p          = subprocess.Popen(c, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

   (out, _) = p.communicate()
   exit_code  = p.wait()

   if exit_code != 0:
      print("[ERROR] Problems running \"{}\": {}".format(c, out.decode('utf-8')))
      sys.exit(1)

   if (len(out.decode('utf-8')) > 0):
      cmd = "docker rmi $(docker images -f \"dangling=true\" -q)"
      p   = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

      p.communicate()
#==================================================================================================================

#==================================================================================================================
# Description: Clean <none> images
# Parameters:  None
# Return:      Nothing. It doesn't matter wether the command finishes correctly or not 

def clean_none_images():
   res      = []

   print("Executing \"clean <none> images\"")

   res      = exec_command("docker images")

   if res[2] != 0:
      print(res[0])
      sys.exit(1)

   # Get all lines in result
   result = re.split(r'\n', res[0])

   # Traverse the array
   for line in result:
      name         = None
      tag          = None
      id           = None

      if re.match(r'^$', line):
         continue

      if re.match(r'^REPOSITORY', line):
         continue

      (name, tag, id, _) = re.split(r'\s+', line, 3)

      if re.match(r'<none>', tag):
         res = exec_command("docker rmi -f {}".format(id))

         if res[2] == 0:
            print("[OK] Image \"{}\" deleted successfully with tag <none>".format(name))
         else:
            print("[ERROR] Deleting imagen \"{}\" with tag <none>: {}".format(name,res[0]))
#==================================================================================================================

#==================================================================================================================
# Description: Clean duplicate docker images
# Parameters:  None
# Return:      Nothing

def clean_duplicate_images(): 
   images   = []
   res      = []

   print("Executing \"clean duplicate images\"")

   res      = get_docker_images()

   if res[2] != 0:
      print(res[0])
      sys.exit(1)

   # Get all lines in result
   result = re.split(r'\n', res[0])

   # Traverse the array
   for line in result:
      name         = None
      tag          = None
      id           = None
      image_exists = False

      if re.match(r'^$', line):
         continue

      if re.match(r'^REPOSITORY', line):
         continue

      (name, tag, id, _) = re.split(r'\s+', line, 3)

      if tag == '<none>' or is_critical_docker_image(name):
         # We don't delete critical images
         continue

      for r in images:
         if r['name'] == name:
            image_exists = True

            r['tags'].append(
               {"tag": "{}".format(tag), "id": "{}".format(id)}
            )

            break

      if not image_exists:
         img = {
            'name': "{}".format(name),
            'tags': [
               {"tag": "{}".format(tag), "id": "{}".format(id)}
            ]
         }
         
         images.append(img)

   for r in images:
      if len(r['tags']) > 1:
         newest = '0.0.0'

         for d in r['tags']:
            ver = re.sub(r'v','', d['tag'])

            if version.parse(ver) > version.parse(newest):
               newest = ver

         for d in r['tags']:
            t = re.sub(r'v','', d['tag'])

            if t == newest:
               # We don't delete the newest version
               continue

            res = exec_command("docker rmi {}:{}".format(r['name'], t))

            if res[2] == 0:
               print("[OK] Image \"{}:{}\" deleted successfully".format(r['name'], t))
            else:
               print("[ERROR] Deleting \"{}:{}\": {}".format(r['name'], t, res[0]))
#==================================================================================================================

#==================================================================================================================
# Description: Execute a command
# Parameters:  Command
# Return:      A list with three elements: stdtout, stderr and exit status

def exec_command(cmd):
   p          = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
   (out, err) = p.communicate()
   exit_code  = p.wait()

   return [out.decode('utf-8'), err, exit_code]
#==================================================================================================================

#==================================================================================================================
# Description: Clean unused docker images
# Parameters:  None
# Return:      Nothing

def clean_unused_images():
   images      = []
   containers  = []
   res         = []

   print("Executing \"clean unused images\"")

   # Get the docker images
   res         = get_docker_images()

   if res[2] != 0:
      print(res[0])
      sys.exit(1)

   images = re.split(r'\n', res[0])

   # Get the containers are running
   res    = exec_command("docker ps --format \"{{.Image}}\"")

   if res[2] != 0:
      print(res[0])
      sys.exit(1)

   containers = re.split(r'\n', res[0])

   for line in images:
      name        = None
      tag         = None
      #id          = None
      image_using = False

      if re.match(r'^$', line):
         continue

      if re.match(r'^REPOSITORY', line):
         continue

      (name, tag, _, _) = re.split(r'\s+', line, 3)

      if is_critical_docker_image(name):
         continue

      # Traverse the running containers
      for c in containers:
         image_using = False

         if re.match(r'^$', c):
            continue

         if re.match(r'^([0-9a-z]){12}$', c):
            # Image name is like this a7a187209cf4
            r = inspect_docker_image(c)

            if r[2] != 0:
               print("[ERROR] Inspecting image \"{}\": {}".format(c, r[0]))
               break

            img = r[0].replace("\n",'')
            img = img.replace('[','')
            img = img.replace(']','')

            if is_critical_docker_image(img):
               continue

            if re.match(r'.*{}.*'.format(name), img):
               image_using = True
               break
         else:
            if is_critical_docker_image(c):
               continue

            if re.match(r'^{}.*'.format(name), c):
               image_using = True
               break

      if not image_using:
         res = exec_command("docker rmi {}:{}".format(name, tag))

         if res[2] == 0:
            print("[OK] Image unused \"{}\" deleted successfully".format(name))
         else:
            print("[ERROR] Deleting \"{}\": {}".format(name, res[0]))
#==================================================================================================================

#==================================================================================================================
# Description: Get docker images
# Parameters:  None
# Return:      The return of the exec_command() function

def get_docker_images():
   return exec_command("docker images")
#==================================================================================================================

#==================================================================================================================
# Description: Check if is a critical docker image
# Parameters:  Name of the image
# Return:      True if is critical, False otherwise

def is_critical_docker_image(name):
   if re.match(r'.*openshift.*',                          name) or \
      re.match(r'.*redhat.*',                             name) or \
      re.match(r'.*kubernetes.*',                         name) or \
      re.match(r'.*kube-.*',                              name) or \
      re.match(r'.*etcd.*',                               name) or \
      re.match(r'.*gluster.*',                            name) or \
      re.match(r'.*heketi.*',                             name) or \
      re.match(r'.*tiller.*',                             name) or \
      re.match(r'.*coreos/cluster-monitoring-operator.*', name) or \
      re.match(r'.*coreos/prometheus-config-reloader.*',  name) or \
      re.match(r'.*coreos/prometheus-operator.*',         name) or \
      re.match(r'.*coreos/configmap-reload.*',            name) or \
      re.match(r'.*weave-.*',                             name) or \
      re.match(r'.*calico.*',                             name) or \
      re.match(r'.*flannel.*',                            name) or \
      re.match(r'.*origin-ansible-service-broker.*',      name):

      return True
   
   return False
#==================================================================================================================

#==================================================================================================================
# Description: Inspect docker image
# Parameters:  Docker image
# Return:      The return of the exec_command() function

def inspect_docker_image(docker_image):
   # Scape {{}}
   return exec_command("docker inspect --format {{{{.RepoTags}}}} {}".format(docker_image))
#==================================================================================================================

# Main
#******************************************************************************************************************
if __name__ == '__main__':
   # Captura de signals
   signal.signal(signal.SIGTERM, signal_handler)
   signal.signal(signal.SIGINT,  signal_handler)

   main()
#******************************************************************************************************************