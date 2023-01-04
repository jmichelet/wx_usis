#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Logiciel pour gérer un spectroscope supportant USIS par une interface graphique.
Seulement testé avec un UVEX (le seul spectro disponible de ce type à ce jour).

-----------------------------------------------------------------------
Copyright (C) <2023> Jacques Michelet.

 This program is free software: you can redistribute it and/or modify
 it under the terms of the GNU General Public License as published by
 the Free Software Foundation, version 3.

 This program is distributed in the hope that it will be useful, but
 WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 General Public License for more details.

 You should have received a copy of the GNU General Public License
 along with this program. If not, see <http://www.gnu.org/licenses/>.
-----------------------------------------------------------------------
"""

import platform
import time
import serial
import serial.tools.list_ports
import wx

if platform.system() == 'Linux':
    import termios

TIMEOUT_VALUE = 3
COULEUR_OK = wx.GREEN
COULEUR_BUSY = wx.YELLOW
COULEUR_ALERT = wx.RED

trad_en = {
    'lien_serie': 'Serial link',
    'aucun_port': 'No available serial port',
    'sortie': 'Exit',
    'sortie_appli': 'Application exit',
    'port_serie': 'Serial port',
    'port_rs232': 'RS-232 communication port',
    'connexion': 'Connection',
    'nom': 'Name',
    'valeur': 'Value',
    'consigne': 'Target',
    'minimum': 'Minimum',
    'maximum': 'Maximum',
    'precision': 'Accuracy',
    'unite': 'Unit',
    'action': 'Go',
    'arret': 'Stop',
    'etalonnage': 'Calibration',
}

trad_fr = {
    'lien_serie': 'Lien série',
    'aucun_port': 'Aucun port série disponible',
    'sortie': 'Sortie',
    'sortie_appli': 'Sortie de l\'application',
    'port_serie': 'Port série',
    'port_rs232': 'Port de communication RS-232',
    'connexion': 'Connexion',
    'nom': 'Nom',
    'valeur': 'Valeur',
    'consigne': 'Consigne',
    'minimum': 'Minimum',
    'maximum': 'Maximum',
    'precision': 'Précision',
    'unite': 'Unité',
    'action': 'Action',
    'arret': 'Arrêt',
    'etalonnage': 'Etalonnage',
}

trad = trad_en

# -------------------------------------------------------------------------------
# -------------------------------------------------------------------------------
# -------------------------------------------------------------------------------


class PortSerie:
    '''
    Permet de stocker le numéro du port série qui sera utilisé par le protocole Usis.
    La mise à jour de ce numéro (attribut de classe) va déclencher l'appel d'une fonction (callback).

    Attributs:
    ----------
    numero : int
    Numéro du port série.

    Methods:
    --------
    ajoute_callback
    Ajoute une fonction de callback qui sera appelée à chaque modification de l'attribut numero.
    '''

    def __init__(self, valeur_initiale=0):
        self._numero = valeur_initiale
        self._callbacks = []

    @property
    def numero(self):
        return self._numero

    @numero.setter
    def numero(self, nouveau_numero):
        self._numero = nouveau_numero
        self._notify_observers(nouveau_numero)

    def _notify_observers(self, nouveau_numero):
        for callback in self._callbacks:
            callback(nouveau_numero)

    def ajoute_callback(self, callback):
        '''
        Enregistre une fonction callback qui sera appelée lors de la modification de _numero.

        Parameters:
        -----------
        callback : function pointer
        Fonction à ajouter.
        '''
        self._callbacks.append(callback)


# -------------------------------------------------------------------------------
# -------------------------------------------------------------------------------
# -------------------------------------------------------------------------------


class SelectionPortSerie(wx.Dialog):
    '''
    Boite de dialogue modale pour sélectionner le port série à utiliser pour le protocole Usis.

    Attributs:
    ----------
    _ports_serie : list of strings
    Liste des noms des ports série possibles.

    Returns:
    --------
    int
    Le numéro du port sélectionné dans la liste ports_serie.
    '''

    def __init__(self, parent, ports_serie):
        '''
        Création de la boite de dialogue.

        Parameters:
        -----------
        parent : WxPython object
        Fenêtre dans lequel inclure la boite de dialogue.
        ports_serie : list of strings
        Liste des noms des ports série possibles.
        '''
        super().__init__(parent, title=wx.GetStockLabel(wx.ID_PREFERENCES, wx.STOCK_NOFLAGS))
        self._ports_serie = ports_serie
        self._numero = -1

        self._generation_ihm()
        self.CenterOnParent()

    def _generation_ihm(self):
        '''
        Construit la liste de sélection et le bouton de validation.
        '''
        global trad

        pl_principal = wx.BoxSizer(wx.VERTICAL)

        # Liste de sélection
        pl_haut = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(self, wx.ID_STATIC, trad['lien_serie'])
        pl_haut.Add(label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.ALIGN_CENTER, 5)
        self.boite_port = wx.ComboBox(
            self,
            wx.ID_ANY,
            choices=self._ports_serie,
            style=wx.CB_DROPDOWN | wx.ALIGN_RIGHT,
        )
        self.boite_port.SetSelection(0)
        self.boite_port.Bind(wx.EVT_COMBOBOX, self._selection)
        pl_haut.Add(self.boite_port, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.ALIGN_CENTER, 5)
        pl_principal.Add(pl_haut, 0, wx.ALL, 5)

        # Bouton de validation
        pl_bas = wx.BoxSizer(wx.VERTICAL)
        bouton_ok = wx.Button(self, label=wx.GetStockLabel(wx.ID_OK))
        pl_bas.Add(bouton_ok)
        pl_principal.Add(pl_bas, 0, wx.RIGHT, 5)

        self.SetSizer(pl_principal)
        pl_principal.SetSizeHints(self)

        # Affectation de l'évènement
        bouton_ok.Bind(wx.EVT_BUTTON, self._fin)

    def _selection(self, evt):
        self._numero = evt.GetSelection()

    def _fin(self, evt):
        '''
        Ferme la boite en renvoyant le numéro sélectionné.
        '''
        if (self._numero < 0):
            self._numero = evt.GetSelection()
        self.EndModal(self._numero)
        self.Destroy()


# -------------------------------------------------------------------------------
# -------------------------------------------------------------------------------
# -------------------------------------------------------------------------------


class ProtocoleUsis():
    '''
    Gestion du dialogue avec un spectroscope compatible USIS.
    Seul le mode série est supporté à ce jour.

    Attributs:
    ----------
    description : list of lists.
    Structure de description complète de l'équipement mise à jour par la fonction 'introspection'.

    Methods:
    --------
    introspection
    Lit l'ensemble des propriétés et des attributs associés.
    et stocke les informations dans la structure 'description'.
    '''

    def __init__(self, port):
        '''
        Parameters:
        -----------
        port : string
        Nom du port série utilisé pour tous les échanges avec le spectroscope.
        '''
        try:
            self._port_serie = serial.Serial(port=port, baudrate=9600, timeout=1, writeTimeout=1)
        except serial.SerialException as se:
            self._port_serie = None
            raise se

        self.description = list()    # Structure de description complète de l'équipement après la phase d'introspection

    def fin(self):
        '''
        Fermeture propre du lien de communication.
        '''
        if self._port_serie:
            self._port_serie.close()

    def _formattage_usis(self, str):
        '''
        Formatage d'une commande RS232 (ajout du checksum, majuscules) au format USIS.
        '''
        str2 = str.strip('\n')
        cs = hex(self._checksum(str2))[2:].zfill(2).upper()
        return (str2 + '*' + cs + '\n')

    def _checksum(self, str):
        '''
        Calcul du checksum d'une chaine de caractères.
        '''
        cks = 0
        for car in bytes(str, 'utf-8'):
            cks = cks ^ car
        return cks

    def _ecriture_lecture(self, trame):
        '''
        Ecriture et lecture de trames via le port série actif.
        '''
        try:
            self._port_serie.reset_input_buffer()    # Nettoyage
            self._port_serie.write(trame.encode('ascii'))    # Envoi du message
            Reply_received = False
            timeout_limit = time.time() + TIMEOUT_VALUE
            timeout_reached = False
            while not Reply_received and not timeout_reached:
                try:
                    if self._port_serie.in_waiting:
                        ligne = str(self._port_serie.readline(), 'ascii')
                        Reply_received = True
                except Exception:
                    time.sleep(3)    # Attente de 3 secondes avant une nouvelle tentative
                timeout_reached = (time.time() >= timeout_limit)
            if Reply_received:
                return ligne    # Pas d'erreur
            if timeout_reached:
                raise serial.SerialException("TIMEOUT")
        except serial.SerialException as se:
            raise se
        except termios.error as te:
            raise serial.SerialException(str(te))

    def echange_usis(self, message):
        '''
        Formatte et envoie le message. Récupère et déformatte la réponse, et gère les erreurs si besoin.

        Parameters:
        -----------
        message : string
        Message à envoyer.

        Returns:
        -------
        (string, string)
        Etat et réponse.

        Raises:
        -------
        RuntimeError
        En cas d'erreur de protocole (non fatale)
        serial.SerialException
        En cas d'erreur de communication (fatale)
        '''
        retour = self._ecriture_lecture(self._formattage_usis(message))
        e = retour.rfind('*')
        l_retour = retour[0:e].split(';')
        if l_retour[0] == "M00":
            return l_retour[-1], l_retour[-2]
        elif l_retour[0][0] == 'C':
            raise serial.SerialException(l_retour[1])
        else:
            raise RuntimeError(l_retour[1])

    # -----------------------------------------------------------------------
    # Ensemble de fonctions permettant l'exploration des fonctionnalités
    # d'un équipement USIS (introspection)
    def info_property_count(self):
        return int(self.echange_usis("INFO;PROPERTY_COUNT\n")[0])

    def info_property_name(self, prop):
        return self.echange_usis("INFO;PROPERTY_NAME;" + str(prop) + '\n')[0]

    def info_property_type(self, prop):
        return self.echange_usis('INFO;PROPERTY_TYPE;' + str(prop) + '\n')[0]

    def info_property_state(self, prop):
        return self.echange_usis('INFO;PROPERTY_STATE;' + str(prop) + '\n')[0]

    def info_property_attr_count(self, prop):
        return int(self.echange_usis('INFO;PROPERTY_ATTR_COUNT;' + str(prop) + '\n')[0])

    def info_property_attr_name(self, prop, attr):
        return self.echange_usis('INFO;PROPERTY_ATTR_NAME;' + str(prop) + ';' + str(attr) + '\n')[0]

    def info_property_attr_mode(self, prop, attr):
        return self.echange_usis('INFO;PROPERTY_ATTR_MODE;' + str(prop) + ';' + str(attr) + '\n')[0]

    def info_property_attr_enum_count(self, prop, attr):
        return int(self.echange_usis('INFO;PROPERTY_ATTR_ENUM_COUNT;' + str(prop) + ';' + str(attr) + '\n')[0])

    def info_property_attr_enum_value(self, prop, enum):
        return self.echange_usis('INFO;PROPERTY_ATTR_ENUM_VALUE;' + str(prop) + ';' + str(enum) + '\n')[0]

    # -----------------------------------------------------------------------
    # Ensemble de fonctions d'échanges avec l'équipement
    def get(self, prop, attr):
        return self.echange_usis('GET;' + str(prop) + ';' + str(attr) + '\n')

    def set(self, prop, consigne):
        return self.echange_usis('SET;' + prop + ';VALUE;' + str(consigne))

    def stop(self, prop):
        return self.echange_usis('STOP;' + prop)

    def calib(self, prop, val_etalon):
        return self.echange_usis('CALIB;' + prop + ';' + str(val_etalon))

    # -----------------------------------------------------------------------

    def introspection(self):
        '''
        Lit l'ensemble des propriétés et des attributs associés
        et stocke les informations dans la structure self.description
        '''
        nb_prop = self.info_property_count()
        for p in range(nb_prop):
            desc_prop = [
                self.info_property_name(p),
                self.info_property_type(p),
                self.info_property_state(p),
                self.info_property_attr_count(p),
            ]
            desc_attr = list()
            for a in range(desc_prop[3]):
                desc_attr.append([
                    self.info_property_attr_name(p, a),
                    self.info_property_attr_mode(p, a),
                ])
                if desc_prop[1] == "ENUM":
                    desc_enum = list()
                    nb_enum = self.info_property_attr_enum_count(p, a)
                    desc_attr[a].append(nb_enum)
                    for e in range(nb_enum):
                        desc_enum.append(self.info_property_attr_enum_value(p, e))
                    desc_attr[a].append(desc_enum)

            desc_prop.append(desc_attr)
            self.description.append(desc_prop)

    def lecture_complete(self):
        '''
        Lit et affiche les valeurs des propriétés. Sert au débogage surtout.
        '''
        for desc_prop in self.description:
            print('\t {0} : type: {1} / etat: {2} / nb_attributs: {3}'.format(
                desc_prop[0],
                desc_prop[1],
                desc_prop[2],
                desc_prop[3],
            ))
            for desc_attr in desc_prop[4]:
                valeur_attribut = self.get(desc_prop[0], desc_attr[0])[0]
                print('\t\t {0} : {1} ({2})'.format(desc_attr[0], valeur_attribut, desc_attr[1]))
                if desc_prop[1] == 'ENUM':
                    print('\t\t\t Valeurs possibles: {0}'.format(desc_attr[3]))


# -------------------------------------------------------------------------------
# -------------------------------------------------------------------------------
# -------------------------------------------------------------------------------


class IHM_Usis(wx.Frame):
    '''
    Gestion graphique d'un spectroscope via le protocole Usis.
    '''

    def __init__(self):
        '''
        Mise en place de l'interface graphique
        '''
        super().__init__(None, title=wx.GetApp().GetAppName())
        self._ihm = dict()    # Références aux objets WxPython non statiques.
        '''
        Drapeaux permettant de metre les valeurs de consigne et d'étalonnage des propriétés à la valeur courante.
        Ce qui permet de minimiser les erreurs lors d'appuis accidentels sur les boutons d'action ou d'étalonnage.
        True => mise à jour requise.
        '''
        self._securite = dict()

        # Vilaine verrue pour les commandes STOP et CALIB
        self._fonctions_motorisees = ['GRATING_ANGLE', 'GRATING_WAVELENGTH', 'FOCUS_POSITION']

        self._ports_serie = list(serial.tools.list_ports.comports())
        self._port_choisi = PortSerie(valeur_initiale=-1)    # Contient le numéro du port sélectionné.

        self._usis = None    # Instance gérant le protocole Usis

        self._chrono = wx.Timer(self, wx.ID_ANY)    # Chrono permettant la mise à jour périodique du graphique

        # Id qui vont permettre de gérer les items des menus
        self._id_serie = wx.NewIdRef()
        self._id_sortie = wx.NewIdRef()

        self._init_ihm()

    def _init_ihm(self):
        '''
        Mise en place du panneau principal et des menus.
        '''
        global trad

        # Barre de menu
        menuBar = wx.MenuBar()
        # Menu Fichier
        menuFile = wx.Menu()
        menuFile.Append(self._id_sortie, trad['sortie'], trad['sortie_appli'])
        menuBar.Append(menuFile, wx.GetStockLabel(wx.ID_FILE))
        # Menu Préférences
        self._menu_connexion = wx.Menu()
        self._menu_connexion.Append(self._id_serie, trad['port_serie'], trad['port_rs232'])
        menuBar.Append(self._menu_connexion, trad['connexion'])
        # Assignation
        self.SetMenuBar(menuBar)

        # Pour OS X, enlever le menu Fichier puisque l'item Exit
        # est pris en charge par l'OS (non testé...)
        if wx.GetOsDescription()[:8] == 'Mac OS X':
            menuBar.Remove(0)
            del menuFile

        self.Bind(wx.EVT_MENU, self._sortie, id=self._id_sortie)
        self.Bind(wx.EVT_MENU, self._selection_port_serie, id=self._id_serie)

    def _sortie(self, evt):
        '''
        Callback déclenché par le menu Fichier->Sortie.
        '''
        if self._usis:
            # Fermeture du port série
            self._usis.fin()
        self.Close()

    def _selection_port_serie(self, evt):
        '''
        Callback déclenchés par le menu Connexion->Port série.
        '''
        global trad
        nom_ports = [port[0] for port in self._ports_serie]
        if not len(nom_ports):
            self._boite_erreur(trad['aucun_port'])
        else:
            # Blocage du menu pour éviter de re-déclencher le callback
            self._menu_connexion.Enable(self._id_serie, False)
            # Boite de sélection du port de communication
            self._port_choisi.ajoute_callback(self._ihm_complet)
            boite_selection = SelectionPortSerie(self, nom_ports)
            self._port_choisi.numero = boite_selection.ShowModal()

    def _ihm_complet(self, numero):
        '''
        Complète la fenêtre avec les informations issues du spectroscope.
        Callback de la boite de sélection du port série.
        '''
        try:
            self._usis = ProtocoleUsis(self._ports_serie[numero][0])
            self._usis.introspection()
            # print(self._usis.description)
            # self._usis.lecture_complete()
            self._tableau_de_bord()
            self._affectation_evenements()
        except serial.SerialException as se:
            self._boite_erreur(str(se), fatal=True)
            self._sortie(None)

    def _tableau_de_bord(self):
        '''
        Construction du graphique de gestion du spectroscope.
        '''
        global trad

        boite = wx.BoxSizer(wx.VERTICAL)

        panneau = wx.Panel(self, wx.ID_ANY)
        grille = wx.FlexGridSizer(rows=len(self._usis.description) + 1, cols=11, vgap=3, hgap=10)

        # Construction de la grille à partir de la description Usis
        self._construction_grille(panneau, grille)

        # Placement de la grille dans le panneau
        panneau.SetSizer(grille)
        grille.Fit(panneau)
        grille.SetSizeHints(panneau)

        # Placement du panneau dans la fenêtre de l'application
        boite.Add(panneau, 0, wx.ALL, 5)
        self.SetSizer(boite)
        boite.Fit(self)
        boite.SetSizeHints(self)

        # Active le rafraichissement toutes les secondes
        self.Bind(wx.EVT_TIMER, self._rafraichissement)
        self._chrono.Start(1000)

    def _construction_grille(self, panneau, grille):
        '''
        Construction de la grille des propriétés à partir de la description fournies par le protocole Usis.
        '''
        for t in [
                trad['nom'],
                trad['valeur'],
                trad['consigne'],
                '',
                '',
                '',
                '',
                trad['minimum'],
                trad['maximum'],
                trad['precision'],
                trad['unite'],
        ]:
            grille.Add(wx.StaticText(panneau, wx.ID_ANY, t), 0, wx.ALIGN_CENTER_HORIZONTAL, 0)

        for id in range(len(self._usis.description)):
            # Les widgets susceptibles de changement vont recevoir un id égal à l'indice de la propriété
            # dans la structure 'description'. Ce qui permet de les relier ultérieurement aux propriétés.
            try:
                desc_prop = self._usis.description[id]
            except RuntimeError as rte:
                self._boite_erreur(str(rte), fatal=True)

            self._ihm[id] = dict()    # Pour pouvoir gérer les évènements ultérieurs
            self._securite[id] = dict()
            etiq_nom = wx.StaticText(panneau, wx.ID_ANY, self.formattage_texte(desc_prop[0]))

            etiq_valeur, \
                edit_valeur, \
                bouton_commande, \
                bouton_arret, \
                edit_etalon, \
                bouton_etalon = self._construction_ligne(
                    panneau,
                    id,
                    desc_prop,
                )

            etiq_min = self._affichage_auxiliaire(panneau, id, 'MIN')
            etiq_max = self._affichage_auxiliaire(panneau, id, 'MAX')
            etiq_prec = self._affichage_auxiliaire(panneau, id, 'PREC')
            etiq_unite = self._affichage_auxiliaire(panneau, id, 'UNIT')

            grille.Add(etiq_nom, 0, wx.ALL | wx.ALIGN_LEFT, 5)
            grille.Add(etiq_valeur, 0, wx.ALL | wx.ALIGN_RIGHT, 1)
            grille.Add(edit_valeur)
            grille.Add(bouton_commande)
            grille.Add(bouton_arret)
            grille.Add(edit_etalon)
            grille.Add(bouton_etalon)
            grille.Add(etiq_min, 0, wx.ALL | wx.ALIGN_RIGHT, 5)
            grille.Add(etiq_max, 0, wx.ALL | wx.ALIGN_RIGHT, 5)
            grille.Add(etiq_prec, 0, wx.ALL | wx.ALIGN_RIGHT, 5)
            grille.Add(etiq_unite, 0, wx.ALL | wx.ALIGN_RIGHT, 5)

    def _construction_ligne(self, panneau, id, desc_prop):
        '''
        Construction de la ligne dans 'panneau' des valeurs et boutons pour une propriété
        donnée par 'id' et 'desc_prop'.
        '''
        global trad

        attribut_valeur = self._recherche_attribut(id, 'VALUE')
        if attribut_valeur:
            try:
                valeur = self._usis.get(desc_prop[0], 'VALUE')[0]
            except RuntimeError as rte:
                self._boite_erreur(str(rte), fatal=True)

            etiq_valeur = wx.StaticText(panneau, id, str(valeur))
            self._ihm[id]['valeur'] = etiq_valeur
            if attribut_valeur[1] == 'RW':
                if desc_prop[1] == 'ENUM':
                    edit_valeur = wx.ComboBox(
                        panneau,
                        id,
                        choices=attribut_valeur[3],
                        style=wx.CB_DROPDOWN | wx.ALIGN_RIGHT,
                    )
                    edit_valeur.SetSelection(attribut_valeur[3].index(valeur))

                else:
                    edit_valeur = wx.TextCtrl(panneau, id, str(valeur), style=wx.ALIGN_RIGHT)

                # Mise en place des boutons d'actions
                self._ihm[id]['consigne'] = edit_valeur
                bouton_commande = wx.Button(panneau, id, trad['action'])
                self._ihm[id]['action'] = bouton_commande
                self._securite[id]['action'] = False

                # Certaines propriétés sont relatives à des moteurs.
                # Ce qui n'est pas explicite dans la spec. Usis. D'où la verrue poilue ...
                if desc_prop[0] in self._fonctions_motorisees:
                    # Oh, la vilaine verrue !
                    bouton_arret = wx.Button(panneau, id, trad['arret'])
                    self._ihm[id]['arret'] = bouton_arret
                    edit_etalon = wx.TextCtrl(panneau, id, str(valeur), style=wx.ALIGN_RIGHT)
                    self._ihm[id]['val_etalon'] = edit_etalon
                    bouton_etalon = wx.Button(panneau, id, trad['etalonnage'])
                    self._ihm[id]['etalon'] = bouton_etalon
                    self._securite[id]['etalon'] = False
                else:
                    bouton_arret = wx.StaticText(panneau, wx.ID_ANY, '')
                    edit_etalon = wx.StaticText(panneau, wx.ID_ANY, '')
                    bouton_etalon = wx.StaticText(panneau, wx.ID_ANY, '')
                    # Fin de la verrue

            else:    # if attribut_valeur[1] == 'RW':
                # Valeur en lecture seule, donc pas de boutons et de saisie de valeur de consigne ou d'étalonnage
                edit_valeur = wx.StaticText(panneau, wx.ID_ANY, '')
                bouton_commande = wx.StaticText(panneau, wx.ID_ANY, '')
                bouton_arret = wx.StaticText(panneau, wx.ID_ANY, '')
                edit_etalon = wx.StaticText(panneau, wx.ID_ANY, '')
                bouton_etalon = wx.StaticText(panneau, wx.ID_ANY, '')

        else:    # if attribut_valeur:
            etiq_valeur = wx.StaticText(panneau, wx.ID_ANY, '')
            edit_valeur = wx.StaticText(panneau, wx.ID_ANY, '')
            bouton_commande = wx.StaticText(panneau, wx.ID_ANY, '')
            bouton_arret = wx.StaticText(panneau, wx.ID_ANY, '')
            edit_etalon = wx.StaticText(panneau, wx.ID_ANY, '')
            bouton_etalon = wx.StaticText(panneau, wx.ID_ANY, '')

        return (etiq_valeur, edit_valeur, bouton_commande, bouton_arret, edit_etalon, bouton_etalon)

    # Fonctions de rafraichissement périodique des valeurs
    # ----------------------------------------------------
    def _rafraichissement(self, evt):
        '''
        Met à jour les informations susceptibles de changer.
        Callback appelé par le _timer.
        '''
        for id in self._ihm.keys():
            nom_prop = self._usis.description[id][0]
            try:
                valeur, etat = self._usis.get(nom_prop, 'VALUE')
            except RuntimeError as rte:
                self._boite_erreur(str(rte))
                break
            except Exception as e:
                self._boite_erreur(str(e), fatal=True)
                break

            self._maj_valeurs(id, valeur, etat)
            self._maj_action(id, valeur, etat)
            self._maj_etalon(id, valeur, etat)

        self.Refresh()

    def _maj_valeurs(self, id, valeur, etat):
        # Zone des valeurs des propriétés
        self._ihm[id]['valeur'].SetLabel(valeur)
        if etat == 'OK':
            self._ihm[id]['valeur'].SetForegroundColour(COULEUR_OK)
        elif etat == 'BUSY':
            self._ihm[id]['valeur'].SetForegroundColour(COULEUR_BUSY)
        else:
            self._ihm[id]['valeur'].SetForegroundColour(COULEUR_ALERT)

    def _maj_action(self, id, valeur, etat):
        # Zone des boutons d'action
        if 'action' in self._ihm[id].keys():
            if etat == 'OK':
                self._ihm[id]['action'].Enable()
                if self._securite[id]['action']:
                    self._ihm[id]['consigne'].SetValue(valeur)
                    self._securite[id]['action'] = False

            else:
                self._ihm[id]['action'].Disable()
                self._securite[id]['action'] = True
                self._securite[id]['etalon'] = True

    def _maj_etalon(self, id, valeur, etat):
        # Zone des boutons d'étalonnage
        if 'etalon' in self._ihm[id].keys():
            if etat == 'OK':
                self._ihm[id]['etalon'].Enable()
                if self._securite[id]['etalon']:
                    self._ihm[id]['val_etalon'].SetValue(valeur)
                    self._securite[id]['etalon'] = False
            else:
                self._ihm[id]['etalon'].Disable()
                self._securite[id]['etalon'] = True
                self._securite[id]['action'] = True

    def _boite_erreur(self, texte, fatal=False):
        '''
        Boite de dialogue d'erreur. 'fatal' désactive le rafraichissement automatique.
        '''
        if fatal:
            self._chrono.Stop()
        dlg = wx.MessageDialog(self, texte, 'Erreur', wx.OK)
        dlg.ShowModal()
        dlg.Destroy()

    def _recherche_attribut(self, id, attribut):
        '''
        Recherche un attribut dans la liste des attributs de la propriété référencée par 'id'.
        '''
        for desc_attr in self._usis.description[id][4]:
            if desc_attr[0] == attribut:
                return desc_attr

        return None

    def _affichage_auxiliaire(self, panneau, id, attribut):
        '''
        Ajout de texte décrivant la valeur d'un attribut du propriété 'id'.
        '''
        desc_attr = self._recherche_attribut(id, attribut)
        if desc_attr:
            val = self._usis.get(self._usis.description[id][0], attribut)[0]
            try:
                val2 = float(val)
            except ValueError:
                val2 = val.lower()
            return wx.StaticText(panneau, wx.ID_ANY, str(val2))
        else:
            return wx.StaticText(panneau, wx.ID_ANY, "")

    # Gestion des évènements, cad de l'appui sur les boutons
    # ------------------------------------------------------
    def _affectation_evenements(self):
        '''
        Tous les boutons d'une même famille (action, arrêt ou étalonnage)ont le même callback.
        Le tri sera fait dans les callbacks.
        '''
        for id in self._ihm.keys():
            if 'action' in self._ihm[id].keys():
                self._ihm[id]['action'].Bind(wx.EVT_BUTTON, self._action)
            if 'arret' in self._ihm[id].keys():
                self._ihm[id]['arret'].Bind(wx.EVT_BUTTON, self._arret)
            if 'etalon' in self._ihm[id].keys():
                self._ihm[id]['etalon'].Bind(wx.EVT_BUTTON, self._etalon)

    def _action(self, evt):
        '''
        Boutons d'actions.
        '''
        # Identification du bouton appuyé et de la propriété qui lui correspond
        id = evt.GetEventObject().GetId()
        nom_prop = self._usis.description[id][0]
        try:
            # Lecture de la valeur de consigne
            if self._ihm[id]['consigne'].__class__.__name__ == 'TextCtrl':
                consigne = self._ihm[id]['consigne'].GetValue()
                if self._usis.description[id][1] == 'FLOAT':
                    consigne = float(consigne)

            elif self._ihm[id]['consigne'].__class__.__name__ == 'ComboBox':
                i = self._ihm[id]['consigne'].GetSelection()
                consigne = self._usis.description[id][4][0][3][i]

            # Action
            self._securite[id]['action'] = True
            self._ihm[id]['action'].Disable()
            valeur, etat = self._usis.set(nom_prop, consigne)
        except RuntimeError as rte:
            self._boite_erreur(str(rte))
            self._ihm[id]['action'].Enable()
        except Exception as e:
            self._boite_erreur(str(e), fatal=True)
            self._sortie(None)

    def _arret(self, evt):
        '''
        Boutons d'arrêt.
        '''
        # Identification du bouton appuyé
        id = evt.GetEventObject().GetId()
        nom_prop = self._usis.description[id][0]
        try:
            # Arret
            valeur, etat = self._usis.stop(nom_prop)
        except RuntimeError as rte:
            self._boite_erreur(str(rte))
            self._ihm[id]['arret'].Enable()
        except Exception as e:
            self._boite_erreur(str(e), fatal=True)
            self._sortie(None)

    def _etalon(self, evt):
        '''
        Boutons d'étalonnage.
        '''
        # Identification du bouton appuyé
        id = evt.GetEventObject().GetId()
        nom_prop = self._usis.description[id][0]
        try:
            # Lecture de la valeur de consigne
            consigne = self._ihm[id]['val_etalon'].GetValue()
            if self._usis.description[id][1] == 'FLOAT':
                val_etalon = float(consigne)
            # Etalonnage
            valeur, etat = self._usis.calib(nom_prop, val_etalon)
        except RuntimeError as rte:
            self._boite_erreur(str(rte))
            self._ihm[id]['etalon'].Enable()
        except Exception as e:
            self._boite_erreur(str(e), fatal=True)
            self._sortie(None)

    @staticmethod
    def formattage_texte(texte):
        '''
        Formatte un texte de type "AA_BBBB" en "Aa bbbb".
        '''
        t1 = texte.replace("_", " ")
        return t1[0].upper() + t1[1:].lower()


# -------------------------------------------------------------------------------
# -------------------------------------------------------------------------------
# -------------------------------------------------------------------------------


class Wx_Usis(wx.App):

    def OnInit(self):

        self.SetAppName('WxUsis')

        trame = IHM_Usis()
        self.SetTopWindow(trame)
        trame.Show()

        return True


# -------------------------------------------------------------------------------
# -------------------------------------------------------------------------------
# -------------------------------------------------------------------------------

if __name__ == '__main__':
    app = Wx_Usis(False)
    app.MainLoop()
