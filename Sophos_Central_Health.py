# Copyright 2019-2020 Sophos Limited
#
# Licensed under the GNU General Public License v3.0(the "License"); you may
# not use this file except in compliance with the License.
#
# You may obtain a copy of the License at:
# https://www.gnu.org/licenses/gpl-3.0.en.html
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing permissions and
# limitations under the License.
#
#
# sophos_central_health.py
#
# Outputs csv file containing full inventory and health status of all devices in Sophos Central
#
#
# By: Michael Curtis and Robert Prechtel
# Date: 29/5/2020
# Version 2.20
# README: This script is an unsupported solution provided by Sophos Professional Services

import requests
import csv
import configparser
# Import OS to allow to check which OS the script is being run on
import os
# Import datetime modules
from datetime import date
from datetime import datetime
# Import time to handle API request limits
import time
# Import getpass for Client Secret
import getpass
today = date.today()
now = datetime.now()
time_stamp = str(now.strftime("%d%m%Y_%H-%M-%S"))
# This list will hold all the sub estates
sub_estate_list = []
# This list will hold all the computers for the report
computer_list = []
# Count the number of total machines across all sub estates
total_machines = 0
# list of high alerts
list_of_high_alerts = []
# list of medium alerts
list_of_medium_alerts = []
# Put the machine name here to break on this machine
debug_machine = 'machine'
# Put the machine name here to break on this machine
debug_sub_estate = 'sub estate'
# Time the script started. Used to renew token when required
start_time = time.time()


# Get Access Token - JWT in the documentation
def get_bearer_token(client, secret, url):
    d = {
                'grant_type': 'client_credentials',
                'client_id': client,
                'client_secret': secret,
                'scope': 'token'
            }
    request_token = requests.post(url, auth=(client, secret), data=d)
    json_token = request_token.json()
    headers = {'Authorization': f"Bearer {json_token['access_token']}"}
    return headers

def get_whoami():
    # We now have our JWT Access Token. We now need to find out if we are a Partner or Organization
    # Partner = MSP
    # Organization = Sophos Central Enterprise Dashboard
    # The whoami URL
    whoami_url = 'https://api.central.sophos.com/whoami/v1'
    request_whoami = requests.get(whoami_url, headers=headers)
    whoami = request_whoami.json()
    # MSP or Sophos Central Enterprise Dashboard
    # We don't use this variable in this script. It returns the organization type
    organization_type = whoami["idType"]
    if whoami["idType"] == "partner":
        organization_header= "X-Partner-ID"
    elif whoami["idType"] == "organization":
        organization_header = "X-Organization-ID"
    else:
        organization_header = "X-Tenant-ID"
    organization_id = whoami["id"]
    # The region_url is used if Sophos Central is a tenant
    region_url = whoami.get('apiHosts', {}).get("dataRegion", None)
    return organization_id, organization_header, organization_type, region_url

def get_all_sub_estates():
    # Add X-Organization-ID to the headers dictionary
    headers[organization_header] = organization_id
    # URL to get the list of tenants
    # Request all tenants
    request_sub_estates = requests.get(f"{'https://api.central.sophos.com/'}{organization_type}{'/v1/tenants?pageTotal=True'}", headers=headers)
    # Convert to JSON
    sub_estate_json = request_sub_estates.json()
    # Find the number of pages we will need to search to get all the sub estates
    total_pages = sub_estate_json["pages"]["total"]
    # Set the keys you want in the list
    sub_estate_keys = ('id', 'name', 'dataRegion')
    while (total_pages != 0):
    # Paged URL https://api.central.sophos.com/organization/v1/tenants?page=2 add total pages in a loop
        request_sub_estates = requests.get(f"{'https://api.central.sophos.com/'}{organization_type}{'/v1/tenants?page='}{total_pages}", headers=headers)
        sub_estate_json = request_sub_estates.json()
        # Add the tenants to the sub estate list
        for all_sub_estates in sub_estate_json["items"]:
            # Make a temporary Dictionary to be added to the sub estate list
            sub_estate_dictionary = {key:value for key, value in all_sub_estates.items() if key in sub_estate_keys}
            sub_estate_list.append(sub_estate_dictionary)
            print(f"Sub Estate - {sub_estate_dictionary['name']}. Sub Estate ID - {sub_estate_dictionary['id']}")
        total_pages -= 1
    # Remove X-Organization-ID from headers dictionary. We don't need this anymore
    del headers[organization_header]
    # Debug code
    print(f"Sub Estates Found: {(len(sub_estate_list))}")

def get_all_computers(sub_estate_token, url, sub_estate_name, alerts_url):
    global headers
    global start_time
    # Get all Computers from sub estates
    # Add pageSize to url and the view of full
    pagesize = 500
    url = (f"{url}{'/endpoints?pageSize='}{pagesize}{'&view=full'}")
    computers_url = url
    # Loop while the page_count is not equal to 0. We have more computers to query
    page_count = 1
    # Count the machines in the sub estate
    machines_in_sub_estate = 0
    while page_count != 0:
        # Script Runtime
        time_since_start = time.time()
        token_time = (time_since_start - start_time)
        # Sub estate to be searched
        # Add X-Tenant-ID to the headers dictionary
        headers['X-Tenant-ID'] = sub_estate_token
        # Should the token be refreshed. Check after 30 minutes
        if token_time >= 1800:
            # print(f"Old Header - {headers}")
            headers = get_bearer_token(client_id, client_secret, token_url)
            headers['X-Tenant-ID'] = sub_estate_token
            # print(f"New Header - {headers}")
            start_time = time.time()
        # Request all Computers
        # Counters to handle API request limits
        retry_counter = 0
        retry_delay = 5
        retry_max = 10
        request_computers = requests.get(computers_url, headers=headers)
        while request_computers.status_code == 429:
            request_computers = requests.get(computers_url, headers=headers)
            print(f" -> Get_All_Computers GET (already found computers={computer_in_sub_estate_count}) result: {request_computers.status_code}")
            if request_computers.status_code == 200:
                break
            if request_computers.status_code != 429:
                print(f" -> ERROR {request_computers.status_code} {request_computers.reason} -> ABORT")
                error_occured = True
                return
            # status_code == 429 - do retry after X seconds till max retry amount reached
            retry_counter = retry_counter + 1
            if retry_counter > retry_max:
                print(
                    f" -> ERROR {request_computers.status_code} {request_computers.reason} -> Maximum retries ({retry_max}) reached. -> ABORT")
                error_occured = True
                return
            print(
                f" -> ERROR {request_computers.status_code} {request_computers.reason} -> Wait {retry_delay} seconds and do {retry_counter}. retry")
            time.sleep(retry_delay)
        if request_computers.status_code == 400:
            print(request_computers.status_code)
        if request_computers.status_code == 403:
            print(f"No access to sub estate - {sub_estate_name}. Status Code - {request_computers.status_code}")
            # Making a dictionary as we have no access to this sub estate
            computer_dictionary = {}
            computer_dictionary['hostname'] = 'No access'
            computer_dictionary['Sub Estate'] = sub_estate_name
            computer_list.append(computer_dictionary)
            break
        # Get all the alerts from the console
        get_all_alerts(sub_estate_token,alerts_url,sub_estate_name)
        # Convert to JSON
        computers_json = request_computers.json()
        # Set the keys you want in the list
        computer_keys = ('id',
                         'hostname',
                         'lastSeenAt',
                         'threats',
                         'service_health',
                         'health',
                         'tamperProtectionEnabled',
                         'ipv4Addresses',
                         'associatedPerson',
                         'Sub Estate',
                         'os',
                         'majorVersion',
                         'type',
                        )
        # Add the computers to the computers list
        for all_computers in computers_json["items"]:
            works = 0
            # Make a temporary Dictionary to be added to the sub estate list
            computer_dictionary = {key:value for key, value in all_computers.items() if key in computer_keys}
            # If no hostname is returned add unknown
            if 'hostname' not in computer_dictionary.keys():
                computer_dictionary['hostname'] = 'Unknown'
            # Debug code. Uncomment the line below if you want to find the machine causing the error
            # print(computer_dictionary['hostname'])
            # This line allows you to debug on a certain computer. Add computer name
            if debug_machine == computer_dictionary['hostname']:
                print('Add breakpoint here')
            # If a machine fails, uncomment the file below to print machine names
            # print(f"Computer name: {computer_dictionary['hostname']}")
            # Sends the last seen date to get_days_since_last_seen and converts this to days
            if 'lastSeenAt' in computer_dictionary.keys():
                computer_dictionary['Last_Seen'] = get_days_since_last_seen(computer_dictionary['lastSeenAt'])
                works = 1
            if works == 0:
                # API is returning incomplete machine fields
                computer_dictionary['hostname'] = 'Unknown'
                # Don't add sub estate if the console is a tenant
                if organization_type != "tenant":
                    computer_dictionary['Sub Estate'] = sub_estate_name
                computer_dictionary['Machine_URL'] = 'N/A'
                computer_list.append(computer_dictionary)
                continue
            if 'health' in computer_dictionary.keys():
                if 'status' in computer_dictionary['health']['services']:
                    computer_dictionary['service_health'] = computer_dictionary['health']['services']['status']
                else:
                    computer_dictionary['service_health'] = 'investigate'
                if 'status' in computer_dictionary['health']['threats']:
                    computer_dictionary['threats'] = computer_dictionary['health']['threats']['status']
                else:
                    computer_dictionary['threats'] = 'investigate'
                # Any filtering you want to do has to done above this line as it changes the health dictionary
                computer_dictionary['health'] = computer_dictionary['health']['overall']
            # Check to see if the key value for platform returns Mac. If so make the OS key equal the Mac version else return the platform name for Windows and Linx
            if 'macOS' in computer_dictionary['os']['platform']:
                computer_dictionary['os'] = str(computer_dictionary['os']['platform']) + ' ' + str(computer_dictionary['os']['majorVersion']) + '.' + str(computer_dictionary['os']['minorVersion']) + '.' + str(computer_dictionary['os']['build'])
            else:
                # Add the build number if the OS is Windows and build number exists
                # Checks the os name is returned. If not add unknowm
                try:
                    computer_dictionary['os']['name']
                    if 'Windows' in computer_dictionary['os']['name'] and 'build' in computer_dictionary['os'] and windows_build_version == 1:
                        computer_dictionary['windows_build'] = (computer_dictionary['os']['build'])
                    computer_dictionary['os'] = computer_dictionary['os']['name']
                except:
                    computer_dictionary['os'] = 'Unknown'
            # Add Cloud fields if the server is in Azure, AWS or GCP via Sophos Central
            # Checks to see if the instanceid is present in the cloud key
            try:
                all_computers['cloud']['instanceId']
                # Checks to see if the cloud servers are required for the report
                if cloud_servers == 1:
                    computer_dictionary['provider'] = all_computers['cloud']['provider']
                    computer_dictionary['instanceid'] = all_computers['cloud']['instanceId']
            except KeyError:
                # Checks to see if the cloud servers are required for the report. If the key is missing for some reason add nothing
                if cloud_servers == 1:
                    computer_dictionary['provider'] = ''
                    computer_dictionary['instanceid'] = ''
            # If a user is returned tidy up the value. It is checking for the key being present
            if 'associatedPerson' in computer_dictionary.keys():
                computer_dictionary['associatedPerson'] = computer_dictionary['associatedPerson']['viaLogin']
            # Checks to see if there is a encryption status
            if 'encryption' in all_computers.keys():
                # I don't think this is the best code. The encryption status is a dictionary, with a list, another dictionary, then the status
                # At present this just reports one drive. The first one in the list. 0
                encryption_status = all_computers['encryption']['volumes']
                # Checks to see if the volume is returned correctly. Sometimes encryption is returned with no volume
                try:
                    volume_returned = encryption_status[0]
                    computer_dictionary['encryption'] = (encryption_status[0]['status'])
                except IndexError:
                    computer_dictionary['encryption'] = 'Unknown'
            # Checks to see if the machine is in a group
            if 'group' in all_computers.keys():
                computer_dictionary['group'] = all_computers['group']['name']
            # Checks if capabilities returns more than nothing
            if len(all_computers['capabilities']) != 0:
                computer_dictionary['capabilities'] = all_computers['capabilities']
            # Get installed products
            # Check if assignedProducts exists. It only works with Windows machines
            if 'assignedProducts' in all_computers.keys():
                for products in all_computers['assignedProducts']:
                    # This loops through the product names and gets the versions. We may not add these to the report
                    product_names = products['code']
                    computer_dictionary[product_names] = products['status']
                    product_version_name = f"v_{product_names}"
                    if products['status'] == 'installed' and versions == 1:
                        computer_dictionary[product_version_name] = products['version']
            if organization_type == "tenant":
                # Provides direct link to the machines if the Sophos Central console is a tenant
                computer_dictionary['Machine_URL'] = make_valid_client_id(computer_dictionary['type'],
                                                                          computer_dictionary['id'])
            else:
                computer_dictionary['Machine_URL'] = 'N/A'
                # Adds the sub estate name to the computer dictionary only if the console is Sophos Central Enterprise Dashboard or MSP
                computer_dictionary['Sub Estate'] = sub_estate_name
            # Checks if we want the MAC Address reported and the MAC Address is returned
            if mac_address == 1 and 'macAddresses' in all_computers:
                computer_dictionary['macAddresses'] = all_computers['macAddresses']
            # Check to see if threat health is exists and is not good. If no, go and find out why
            if 'health' in computer_dictionary and 'good' != computer_dictionary['health']:
                medium_alert_count, high_alert_count, list_of_computer_medium_alerts, list_of_computer_high_alerts = get_machine_alerts(computer_dictionary['id'],computer_dictionary['hostname'],alerts_url)
                # Adding details to the report where the Alert count is zero as the Health status is not good
                # This has been caused by a non Alert event
                if high_alert_count == 0:
                    # Bad, Good, Bad
                    if 'good' != computer_dictionary['service_health']:
                        high_alert_count += 1
                        list_of_computer_high_alerts.append('Broken Service(s)')
                    # Adding bad Threat to the high alert column as this is not an Alert
                    # Bad, Bad, Good
                    if 'bad' == computer_dictionary['threats']:
                        high_alert_count += 1
                        list_of_computer_high_alerts.append('Investigation Required')
                    # Adding Bad, Good, Good to the report
                    if 'bad' == computer_dictionary['health'] and computer_dictionary['threats'] == 'good' and computer_dictionary['service_health'] == 'good':
                        high_alert_count += 1
                        list_of_computer_high_alerts.append('Investigation Required')
                if medium_alert_count == 0:
                    # Adding Suspicious, Good, Good to the report
                    if 'suspicious' == computer_dictionary['health'] and computer_dictionary['threats'] == 'good' and computer_dictionary['service_health'] == 'good':
                        medium_alert_count += 1
                        list_of_computer_medium_alerts.append('Investigation Required')
                alert_count = 0
                # Finds the first column for high alerts. EDB and Single console have different number of columns
                high_alert_start_column = report_column_order.index('tamperProtectionEnabled') + 2
                for alert in list_of_computer_high_alerts:
                    computer_dictionary[f"high_alerts_{alert_count}"] = alert
                    # Checks to see if another alert column is needed
                    if f'high_alerts_{alert_count}' not in report_column_order:
                        # Adds the Alert to the column order list in the right place. Starts at the column after Tamper Enabled
                        report_column_order.insert(high_alert_start_column + alert_count, f"high_alerts_{alert_count}")
                        # Adds the alert column name list in the right place. Starts at the column after Tamper Enabled
                        report_column_names.insert(high_alert_start_column + alert_count, f"High Alert No. {alert_count+1}")
                    alert_count += 1
                alert_count = 0
                # Finds the first column for medium alerts. We don't know how many highs we will have
                medium_alert_start_column = report_column_order.index('number_medium_alerts') + 1
                for alert in list_of_computer_medium_alerts:
                    computer_dictionary[f"medium_alerts_{alert_count}"] = alert
                    # Checks to see if another alert column is needed
                    if f'medium_alerts_{alert_count}' not in report_column_order:
                        # Adds the Alert to the column order list in the right place. Starts at column 17
                        report_column_order.insert(medium_alert_start_column + alert_count, f"medium_alerts_{alert_count}")
                        # Adds the alert column name list in the right place. Starts at column 17
                        report_column_names.insert(medium_alert_start_column + alert_count, f"Medium Alert No. {alert_count+1}")
                    alert_count += 1
                # Adds the result of the get_machine_alerts to the computer_dictionary
                # Making sure there are no 0 counts in the report
                if high_alert_count != 0:
                    computer_dictionary['number_high_alerts'] = high_alert_count
                if medium_alert_count != 0:
                    computer_dictionary['number_medium_alerts'] = medium_alert_count
            computer_list.append(computer_dictionary)
        # Check to see if you have more than one page of machines by checking if nextKey exists
        # We need to check if we need to page through lots of computers
        if 'nextKey' in computers_json['pages']:
            next_page = computers_json['pages']['nextKey']
            # Change URL to get the next page of computers
            # Example https://api-us01.central.sophos.com/endpoint/v1/endpoints?pageFromKey=<next-key>
            computers_url = f"{url}{'&pageFromKey='}{next_page}"
            # Add the number of machines on this page
            machines_in_sub_estate += len(computers_json['items'])
        else:
            # Add the number of machines on the last page
            machines_in_sub_estate += len(computers_json['items'])
            # If we don't get another nextKey set page_count to 0 to stop looping
            page_count = 0
    if machines_in_sub_estate == 0:
        # Making a dictionary as no dictionary made due to no machines in the sub estate
        computer_dictionary = {}
        computer_dictionary['hostname'] = 'Empty sub estate'
        computer_dictionary['Sub Estate'] = sub_estate_name
        computer_list.append(computer_dictionary)
    print(f'Checked sub estate - {sub_estate_name}. Machines in sub estate {machines_in_sub_estate}')
    return (machines_in_sub_estate)

def get_days_since_last_seen(report_date):
    # https://www.programiz.com/python-programming/datetime/strptime
    # Converts report_date from a string into a DataTime
    convert_last_seen_to_a_date = datetime.strptime(report_date, "%Y-%m-%dT%H:%M:%S.%f%z")
    # Remove the time from convert_last_seen_to_a_date
    convert_last_seen_to_a_date = datetime.date(convert_last_seen_to_a_date)
    # Converts date to days
    days = (today - convert_last_seen_to_a_date).days
    return days

def make_valid_client_id(os, machine_id):
    # Characters to be removed
    # https://central.sophos.com/manage/server/devices/servers/b10cc611-7805-7419-e9f0-46947a4ab60e/summary
    # https://central.sophos.com/manage/endpoint/devices/computers/60b19085-7bbf-44ff-3a67-e58a3c4e14b1/summary
    server_url = 'https://central.sophos.com/manage/server/devices/servers/'
    endpoint_url = 'https://central.sophos.com/manage/endpoint/devices/computers/'
    # Remove the - from the id
    remove_characters_from_id = ['-']
    for remove_each_character in remove_characters_from_id:
        machine_id = machine_id.replace(remove_each_character, '')
    new_machine_id = list(machine_id)
    # Rotates the characters
    new_machine_id[::2], new_machine_id[1::2] = new_machine_id[1::2], new_machine_id[::2]
    for i in range(8, 28, 5):
        new_machine_id.insert(i, '-')
    new_machine_id = ''.join(new_machine_id)
    if os == 'computer':
        machine_url = endpoint_url + new_machine_id
    else:
        machine_url = server_url + new_machine_id
    return (machine_url)

def read_config():
    config = configparser.ConfigParser()
    config.read('sophos_central_health.config')
    config.sections()
    client_id = config['DEFAULT']['ClientID']
    client_secret = config['DEFAULT']['ClientSecret']
    if client_secret == '':
        client_secret = getpass.getpass(prompt='Enter Client Secret: ', stream=None)
    report_name = config['REPORT']['ReportName']
    report_file_path = config['REPORT']['ReportFilePath']
    mac_address = config.getint('EXTRA_FIELDS', 'MAC_Address')
    versions = config.getint('EXTRA_FIELDS', 'Versions')
    windows_build_version = config.getint('EXTRA_FIELDS', 'Windows_Build_Version')
    cloud_servers = config.getint('EXTRA_FIELDS', 'Cloud_Servers')
    # Checks if the last character of the file path contains a \ or / if not add one
    if report_file_path[-1].isalpha():
        if os.name != "posix":
            report_file_path = report_file_path + "\\"
        else:
            report_file_path = report_file_path + "/"
    return(client_id,client_secret,report_name,report_file_path,mac_address,versions, windows_build_version,cloud_servers)

def report_field_names():
    report_column_names = ['Machine URL',
                  'Sub Estate',
                  'Hostname',
                  'Type',
                  'Cloud Provider',
                  'InstanceID',
                  'OS',
                  'Windows Build',
                  'Encrypted Status',
                  'Last Seen Date',
                  'Days Since Last Seen',
                  'Health',
                  'Threats',
                  'Service Health',
                  'Tamper Enabled',
                  'No. High Alerts',
                  'No. Medium Alerts',
                  'Capabilities',
                  'Group',
                  'Core Agent',
                  'Core Agent Version',
                  'Endpoint Protection',
                  'Endpoint Protection Version',
                  'Intercept X',
                  'Intercept X Version',
                  'Device Encryption',
                  'Device Encryption Version',
                  'MTR',
                  'MTR Version',
                  'IP Addresses',
                  'Mac Addresses',
                  'Last User',
                  'id',
                  ]
    report_column_order = ['Machine_URL',
             'Sub Estate',
             'hostname',
             'type',
             'provider',
             'instanceid',
             'os',
             'windows_build',
             'encryption',
             'lastSeenAt',
             'Last_Seen',
             'health',
             'threats',
             'service_health',
             'tamperProtectionEnabled',
             'number_high_alerts',
             'number_medium_alerts',
             'capabilities',
             'group',
             'coreAgent',
             'v_coreAgent',
             'endpointProtection',
             'v_endpointProtection',
             'interceptX',
             'v_interceptX',
             'deviceEncryption',
             'v_deviceEncryption',
             'mtr',
             'v_mtr',
             'ipv4Addresses',
             'macAddresses',
             'associatedPerson',
             'id',
             ]
    return(report_column_names,report_column_order)

def get_machine_alerts(computer_id, hostname, alerts_url):
    # Makes two lists of store the alert descripts
    list_of_computer_medium_alerts = []
    list_of_computer_high_alerts = []
    print(f'Finding alerts for machine:{hostname} - {computer_id}')
    # Sets the alert count to zero
    medium_alert_count = 0
    high_alert_count = 0
    # Checks the comuputer_id in the list_of_medium_alerts to see if the machine has an alert
    for machine_id in list_of_medium_alerts:
        if machine_id['managedAgent'] == computer_id:
            medium_alert_count += 1
            list_of_computer_medium_alerts.append(machine_id['description'])
    # Checks the comuputer_id in the list_of_high_alerts to see if the machine has an alert
    for machine_id in list_of_high_alerts:
        if machine_id['managedAgent'] == computer_id:
            high_alert_count += 1
            list_of_computer_high_alerts.append(machine_id['description'])
    # This line allows you to debug on a certain computer. Add computer name
    if hostname == debug_machine:
        print(f'Put breakpoint here - Debug Machine - {debug_machine}')
    # returns the results
    return medium_alert_count, high_alert_count, list_of_computer_medium_alerts, list_of_computer_high_alerts

def get_all_alerts(tenant_token, url,sub_estate_name):
    # Get all the alerts from the console
    # Loop while the page_count is not equal to 0. We have more computers to query
    page_count = 1
    # Debug - Put the sub estate name you want to debug in the line below
    if sub_estate_name == debug_sub_estate:
        print(f'Put breakpoint here - sub estate - {sub_estate_name}')
    alert_search_url = url
    # Set the keys we need from the alert
    alert_keys = (
        'id',
        'allowedActions',
        'category',
        'description',
        'raisedAt',
        'severity',
        'type',
        'managedAgent',
    )
    while page_count != 0:
        # Tenant to be searched
        tenant_id = tenant_token
        # Add X-Tenant-ID to the headers dictionary
        headers['X-Tenant-ID'] = tenant_id
        # Request all Computers
        request_computers = requests.get(alert_search_url, headers=headers)
        # Convert to JSON
        alerts_json = request_computers.json()
        # Debug - Put the sub estate name you want to debug in the line below
        if sub_estate_name == debug_sub_estate:
            print(f'Put breakpoint here - sub estate - {sub_estate_name}')
        for alerts in alerts_json['items']:
            # Make a temporary Dictionary to be added keys needed for the alerts
            alerts_dictionary = {key: value for key, value in alerts.items() if key in alert_keys}
            if alerts['severity'] == 'high':
                # Get the Endpoint ID and reconfigure the alerts_dictionary
                # Check to see if the alert has an ID
                if 'id' in alerts_dictionary['managedAgent']:
                    alerts_dictionary['managedAgent'] = alerts_dictionary['managedAgent']['id']
                else:
                    alerts_dictionary['managedAgent'] = 'Console'
                list_of_high_alerts.append(alerts_dictionary)
            if alerts['severity'] == 'medium':
                # Get the Endpoint ID and reconfigure the alerts_dictionary
                # Check to see if the alert has an ID
                if 'id' in alerts_dictionary['managedAgent']:
                    alerts_dictionary['managedAgent'] = alerts_dictionary['managedAgent']['id']
                else:
                    alerts_dictionary['managedAgent'] = 'Console'
                list_of_medium_alerts.append(alerts_dictionary)
        if 'nextKey' in alerts_json['pages']:
            next_page = alerts_json['pages']['nextKey']
            # Change URL to get the next page of computers
            # Example https://api-us01.central.sophos.com/endpoint/v1/endpoints?pageFromKey=<next-key>
            alert_search_url = f"{url}{'&pageFromKey='}{next_page}"
            # Debug - Put the sub estate name you want to debug in the line below
            if sub_estate_name == debug_sub_estate:
                print(f'Put breakpoint here - sub estate - {sub_estate_name}')
        else:
            # If we don't get another nextKey set page_count to 0 to stop looping
            page_count = 0
    # Debug - Put the sub estate name you want to debug in the line below
    if sub_estate_name == debug_sub_estate:
        print(f'Put breakpoint here - sub estate - {sub_estate_name}')
    return (list_of_medium_alerts, list_of_high_alerts)

def print_report():
    full_report_path = f"{report_file_path}{report_name}{time_stamp}{'.csv'}"
    # Remove the report columns that aren't required from the extra fields selection
    if mac_address == 0:
        report_column_names.remove('Mac Addresses')
        report_column_order.remove('macAddresses')
    if versions == 0:
        report_column_names.remove('Intercept X Version')
        report_column_names.remove('Endpoint Protection Version')
        report_column_names.remove('Core Agent Version')
        report_column_names.remove('Device Encryption Version')
        report_column_names.remove('MTR Version')
        report_column_order.remove('v_interceptX')
        report_column_order.remove('v_endpointProtection')
        report_column_order.remove('v_coreAgent')
        report_column_order.remove('v_deviceEncryption')
        report_column_order.remove('v_mtr')
    if windows_build_version == 0:
        report_column_names.remove('Windows Build')
        report_column_order.remove('windows_build')
    if cloud_servers == 0:
        report_column_names.remove('Cloud Provider')
        report_column_names.remove('InstanceID')
        report_column_order.remove('provider')
        report_column_order.remove('instanceid')
    if organization_type == "tenant":
        # Removes sub estate name from report if the console is a single tenant
        report_column_names.remove('Sub Estate')
        report_column_order.remove('Sub Estate')
    with open(full_report_path, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(report_column_names)
    # Sets the column order
    with open(full_report_path, 'a+', encoding='utf-8', newline='') as output_file:
        dict_writer = csv.DictWriter(output_file, report_column_order)
        dict_writer.writerows(computer_list)



client_id, client_secret, report_name, report_file_path, mac_address, versions, windows_build_version,cloud_servers = read_config()
token_url = 'https://id.sophos.com/api/v2/oauth2/token'
headers = get_bearer_token(client_id, client_secret, token_url)
organization_id, organization_header, organization_type, region_url = get_whoami()
report_column_names, report_column_order = report_field_names()
all_machines_count = 0
if organization_type != "tenant":
    print(f"Sophos Central is a {organization_type}")
    get_all_sub_estates()
    # fieldnames, order, versions = report_field_names()
    for sub_etates_in_list in range(len(sub_estate_list)):
        sub_estate = sub_estate_list[sub_etates_in_list]
        # Debug - If you want to test one particular sub estate put the ID in the line below and uncomment the line
        # sub_estate['id'] = ''
        total_machines = get_all_computers(sub_estate['id'], f"{'https://api-'}{sub_estate['dataRegion']}{'.central.sophos.com/endpoint/v1'}",
                                           sub_estate['name'],
                                           f"{'https://api-'}{sub_estate['dataRegion']}{'.central.sophos.com/common/v1/alerts?pageSize=100'}"
                                           )
        all_machines_count += total_machines
else:
    report_column_names, report_column_order = report_field_names()
    print(f"Sophos Central is a {organization_type}")
    # Removes sub estate name from report if the console is a single tenant
    # report_column_names.remove('Sub Estate')
    # report_column_order.remove('Sub Estate')
    total_machines = get_all_computers(organization_id,
                                       f"{region_url}{'/endpoint/v1'}",
                                       organization_type,
                                       f"{region_url}{'/common/v1/alerts?pageSize=100'}"
                                       )
    all_machines_count += total_machines
print(f"Total Number Of Machines: {all_machines_count}")
print_report()